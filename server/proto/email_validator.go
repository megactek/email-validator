package proto

import (
	"context"

	"google.golang.org/grpc"
	"google.golang.org/protobuf/types/known/emptypb"
)

// ValidationStatus represents the status of an email validation
type ValidationStatus int32

const (
	ValidationStatus_UNKNOWN    ValidationStatus = 0
	ValidationStatus_VALID      ValidationStatus = 1
	ValidationStatus_INVALID    ValidationStatus = 2
	ValidationStatus_ERROR      ValidationStatus = 3
	ValidationStatus_DISPOSABLE ValidationStatus = 4
)

// EmailRequest is a request to validate an email
type EmailRequest struct {
	Email string
}

// ValidationResponse is a response with validation results
type ValidationResponse struct {
	Email      string
	Valid      bool
	Disposable bool
	Reason     string
}

// BatchRequest is a request to validate multiple emails
type BatchRequest struct {
	Emails []string
}

// BatchResponse contains multiple validation results
type BatchResponse struct {
	Results []*ValidationResponse
}

// StatsResponse contains validation statistics
type StatsResponse struct {
	ValidCount      int64
	InvalidCount    int64
	UnknownCount    int64
	DisposableCount int64
	TotalCount      int64
	UptimeSeconds   int64
}

// EmailValidatorServiceServer is the server API for EmailValidatorService
type EmailValidatorServiceServer interface {
	ValidateEmail(context.Context, *EmailRequest) (*ValidationResponse, error)
	ValidateEmails(context.Context, *BatchRequest) (*BatchResponse, error)
	ValidateEmailStream(EmailValidatorService_ValidateEmailStreamServer) error
	GetStats(context.Context, *emptypb.Empty) (*StatsResponse, error)
}

// EmailValidatorService_ValidateEmailStreamServer is the server API for streaming validation
type EmailValidatorService_ValidateEmailStreamServer interface {
	Send(*ValidationResponse) error
	Recv() (*EmailRequest, error)
	grpc.ServerStream
}

// UnimplementedEmailValidatorServiceServer can be embedded to have forward compatible implementations
type UnimplementedEmailValidatorServiceServer struct {
}

func (s *UnimplementedEmailValidatorServiceServer) ValidateEmail(ctx context.Context, req *EmailRequest) (*ValidationResponse, error) {
	return nil, nil
}

func (s *UnimplementedEmailValidatorServiceServer) ValidateEmails(ctx context.Context, req *BatchRequest) (*BatchResponse, error) {
	return nil, nil
}

func (s *UnimplementedEmailValidatorServiceServer) ValidateEmailStream(srv EmailValidatorService_ValidateEmailStreamServer) error {
	return nil
}

func (s *UnimplementedEmailValidatorServiceServer) GetStats(ctx context.Context, req *emptypb.Empty) (*StatsResponse, error) {
	return nil, nil
}

// RegisterEmailValidatorServiceServer registers the server with the gRPC server
func RegisterEmailValidatorServiceServer(s *grpc.Server, srv EmailValidatorServiceServer) {
	// This is a stub implementation
}
