package main

import (
	"context"
	"flag"
	"fmt"
	"log"
	"net"
	"sync"
	"sync/atomic"
	"time"

	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
	"google.golang.org/protobuf/types/known/emptypb"

	"github.com/megactek/email-validator/proto"
	"github.com/megactek/email-validator/validator"
)

// Server implements the EmailValidatorService
type Server struct {
	proto.UnimplementedEmailValidatorServiceServer
	validator   *validator.EmailValidator
	rateLimiter *RateLimiter

	// Statistics
	validCount      int64
	invalidCount    int64
	unknownCount    int64
	disposableCount int64
	totalCount      int64

	// For tracking the time the service started
	startTime time.Time
}

// RateLimiter implements rate limiting for API requests
type RateLimiter struct {
	requestsPerSecond int
	requestCounter    int
	lastReset         time.Time
	mutex             sync.Mutex
}

// NewRateLimiter creates a new rate limiter
func NewRateLimiter(requestsPerSecond int) *RateLimiter {
	return &RateLimiter{
		requestsPerSecond: requestsPerSecond,
		requestCounter:    0,
		lastReset:         time.Now(),
	}
}

// Allow checks if a request should be allowed under the rate limit
func (rl *RateLimiter) Allow() bool {
	rl.mutex.Lock()
	defer rl.mutex.Unlock()

	now := time.Now()
	elapsed := now.Sub(rl.lastReset)

	// Reset counter every second
	if elapsed >= time.Second {
		rl.requestCounter = 0
		rl.lastReset = now
	}

	if rl.requestCounter >= rl.requestsPerSecond {
		return false
	}

	rl.requestCounter++
	return true
}

// ValidateEmail handles single email validation requests
func (s *Server) ValidateEmail(ctx context.Context, req *proto.EmailRequest) (*proto.ValidationResponse, error) {
	if !s.rateLimiter.Allow() {
		return nil, status.Error(codes.ResourceExhausted, "Rate limit exceeded")
	}

	email := req.Email
	if email == "" {
		return nil, status.Error(codes.InvalidArgument, "Email cannot be empty")
	}

	result := s.validator.ValidateEmail(email)

	// Update statistics
	s.updateStats(result)

	return &proto.ValidationResponse{
		Email:      email,
		Valid:      result.Valid,
		Disposable: result.Disposable,
		Reason:     result.Reason,
	}, nil
}

// ValidateEmails handles batch validation requests
func (s *Server) ValidateEmails(ctx context.Context, req *proto.BatchRequest) (*proto.BatchResponse, error) {
	if !s.rateLimiter.Allow() {
		return nil, status.Error(codes.ResourceExhausted, "Rate limit exceeded")
	}

	if len(req.Emails) == 0 {
		return nil, status.Error(codes.InvalidArgument, "Batch cannot be empty")
	}

	results := make([]*proto.ValidationResponse, 0, len(req.Emails))

	for _, email := range req.Emails {
		result := s.validator.ValidateEmail(email)

		// Update statistics
		s.updateStats(result)

		results = append(results, &proto.ValidationResponse{
			Email:      email,
			Valid:      result.Valid,
			Disposable: result.Disposable,
			Reason:     result.Reason,
		})
	}

	return &proto.BatchResponse{
		Results: results,
	}, nil
}

// ValidateEmailStream handles streaming validation requests
func (s *Server) ValidateEmailStream(stream proto.EmailValidatorService_ValidateEmailStreamServer) error {
	for {
		req, err := stream.Recv()
		if err != nil {
			return err
		}

		if !s.rateLimiter.Allow() {
			return status.Error(codes.ResourceExhausted, "Rate limit exceeded")
		}

		email := req.Email
		if email == "" {
			continue // Skip empty emails
		}

		result := s.validator.ValidateEmail(email)

		// Update statistics
		s.updateStats(result)

		// Send response back to client
		err = stream.Send(&proto.ValidationResponse{
			Email:      email,
			Valid:      result.Valid,
			Disposable: result.Disposable,
			Reason:     result.Reason,
		})

		if err != nil {
			return err
		}
	}
}

// GetStats returns current validation statistics
func (s *Server) GetStats(ctx context.Context, _ *emptypb.Empty) (*proto.StatsResponse, error) {
	uptime := time.Since(s.startTime).Seconds()

	return &proto.StatsResponse{
		ValidCount:      atomic.LoadInt64(&s.validCount),
		InvalidCount:    atomic.LoadInt64(&s.invalidCount),
		UnknownCount:    atomic.LoadInt64(&s.unknownCount),
		DisposableCount: atomic.LoadInt64(&s.disposableCount),
		TotalCount:      atomic.LoadInt64(&s.totalCount),
		UptimeSeconds:   int64(uptime),
	}, nil
}

// updateStats updates the validation statistics
func (s *Server) updateStats(result validator.Result) {
	atomic.AddInt64(&s.totalCount, 1)

	if result.Valid {
		atomic.AddInt64(&s.validCount, 1)
	} else {
		atomic.AddInt64(&s.invalidCount, 1)
	}

	if result.Disposable {
		atomic.AddInt64(&s.disposableCount, 1)
	}

	if result.Reason == "Could not connect to any mail server" {
		atomic.AddInt64(&s.unknownCount, 1)
	}
}

func main() {
	// Command line flags
	port := flag.Int("port", 50051, "The server port")
	rateLimit := flag.Int("rate-limit", 20, "Maximum checks per minute per domain")
	ipFile := flag.String("ips-file", "source_ips.txt", "File with source IPs")
	disposableFile := flag.String("disposable-file", "disposable_domains.txt", "File with disposable domains")

	flag.Parse()

	// Load source IPs
	sourceIPs, err := validator.LoadSourceIPs(*ipFile)
	if err != nil {
		log.Printf("Warning: Could not load source IPs: %v", err)
		sourceIPs = []string{} // Empty array if file not found
	}
	log.Printf("Loaded %d source IPs", len(sourceIPs))

	// Load disposable domains
	disposableDomains, err := validator.LoadDisposableDomains(*disposableFile)
	if err != nil {
		log.Printf("Warning: Could not load disposable domains: %v", err)
		disposableDomains = make(map[string]bool) // Empty map if file not found
	}
	log.Printf("Loaded %d disposable domains", len(disposableDomains))

	// Create email validator
	config := validator.Config{
		SourceIPs:         sourceIPs,
		DisposableDomains: disposableDomains,
		RateLimit:         *rateLimit,
		Timeout:           10 * time.Second,
	}

	emailValidator := validator.NewEmailValidator(config)

	// Create server
	server := &Server{
		validator:   emailValidator,
		rateLimiter: NewRateLimiter(100), // 100 requests per second
		startTime:   time.Now(),
	}

	// Start gRPC server
	lis, err := net.Listen("tcp", fmt.Sprintf(":%d", *port))
	if err != nil {
		log.Fatalf("Failed to listen: %v", err)
	}

	grpcServer := grpc.NewServer()
	proto.RegisterEmailValidatorServiceServer(grpcServer, server)

	log.Printf("Server started on port %d", *port)
	if err := grpcServer.Serve(lis); err != nil {
		log.Fatalf("Failed to serve: %v", err)
	}
}
