package validator

import (
	"bufio"
	"fmt"
	"log"
	"math/rand"
	"net"
	"net/smtp"
	"os"
	"regexp"
	"strings"
	"sync"
	"time"
)

// ValidationResult represents the result of email validation
type ValidationResult struct {
	Email  string `json:"email"`
	Valid  *bool  `json:"valid"`
	Reason string `json:"reason,omitempty"`
	Status string `json:"status"`
}

// Config holds configuration for the email validator
type Config struct {
	Timeout           time.Duration
	RetryLimit        int
	MaxWorkers        int
	MaxPerMinute      int
	SenderEmail       string
	TempFilePrefix    string
	SourceIPs         []string        // Source IP addresses to rotate through
	DisposableDomains map[string]bool // Map of disposable email domains
	RateLimit         int             // Maximum checks per minute
}

// DefaultConfig creates a default configuration
func DefaultConfig() Config {
	return Config{
		Timeout:           10 * time.Second,
		RetryLimit:        2,
		MaxWorkers:        1,
		MaxPerMinute:      20,
		SenderEmail:       "verify@example.com",
		TempFilePrefix:    "validator_",
		SourceIPs:         []string{},
		DisposableDomains: make(map[string]bool),
	}
}

// DomainThrottler manages domain-specific rate limiting to avoid triggering anti-spam measures
type DomainThrottler struct {
	domainAccess map[string][]time.Time
	domainErrors map[string]int
	maxPerDomain int
	defaultDelay time.Duration
	mu           sync.Mutex
}

// NewDomainThrottler creates a new domain throttler
func NewDomainThrottler(defaultDelaySeconds, maxPerDomain int) *DomainThrottler {
	return &DomainThrottler{
		domainAccess: make(map[string][]time.Time),
		domainErrors: make(map[string]int),
		maxPerDomain: maxPerDomain,
		defaultDelay: time.Duration(defaultDelaySeconds) * time.Second,
		mu:           sync.Mutex{},
	}
}

// WaitForDomain waits if necessary before accessing a domain
func (d *DomainThrottler) WaitForDomain(domain string) {
	d.mu.Lock()
	defer d.mu.Unlock()

	now := time.Now()

	// Initialize domain if not seen before
	if _, ok := d.domainAccess[domain]; !ok {
		d.domainAccess[domain] = []time.Time{}
		d.domainErrors[domain] = 0
	}

	// Remove access times older than 60 seconds
	var recentAccesses []time.Time
	for _, accessTime := range d.domainAccess[domain] {
		if now.Sub(accessTime) <= 60*time.Second {
			recentAccesses = append(recentAccesses, accessTime)
		}
	}
	d.domainAccess[domain] = recentAccesses

	// Calculate delay based on error count and recent accesses
	errorCount := d.domainErrors[domain]
	recentAccessCount := len(d.domainAccess[domain])

	// Exponential backoff based on errors
	delay := d.defaultDelay * time.Duration(1<<uint(min(errorCount, 5)))

	// Add additional delay if we've accessed this domain many times recently
	if recentAccessCount >= d.maxPerDomain/2 {
		delay += time.Duration(recentAccessCount) * time.Second
	}

	// If we have recent accesses, ensure minimum time between them
	if len(d.domainAccess[domain]) > 0 {
		lastAccess := d.domainAccess[domain][len(d.domainAccess[domain])-1]
		timeSinceLastAccess := now.Sub(lastAccess)
		if timeSinceLastAccess < delay {
			d.mu.Unlock()
			time.Sleep(delay - timeSinceLastAccess)
			d.mu.Lock()
		}
	}

	// Record this access
	d.domainAccess[domain] = append(d.domainAccess[domain], time.Now())
}

// ReportSuccess reports successful domain access
func (d *DomainThrottler) ReportSuccess(domain string) {
	d.mu.Lock()
	defer d.mu.Unlock()
	if _, ok := d.domainErrors[domain]; ok {
		d.domainErrors[domain] = max(0, d.domainErrors[domain]-1)
	}
}

// ReportError reports domain access error to increase backoff
func (d *DomainThrottler) ReportError(domain string) {
	d.mu.Lock()
	defer d.mu.Unlock()
	if _, ok := d.domainErrors[domain]; ok {
		d.domainErrors[domain]++
	}
}

// IPRotator rotates between multiple source IP addresses if available
type IPRotator struct {
	ips        []string
	currentIdx int
	mu         sync.Mutex
}

// NewIPRotator creates a new IP rotator
func NewIPRotator(ips []string) *IPRotator {
	return &IPRotator{
		ips:        ips,
		currentIdx: 0,
		mu:         sync.Mutex{},
	}
}

// GetNextIP gets the next IP in the rotation
func (r *IPRotator) GetNextIP() string {
	if len(r.ips) == 0 {
		return ""
	}

	r.mu.Lock()
	defer r.mu.Unlock()

	ip := r.ips[r.currentIdx]
	r.currentIdx = (r.currentIdx + 1) % len(r.ips)
	return ip
}

// RateLimiter ensures we don't exceed the rate limit
type RateLimiter struct {
	maxPerMinute int
	interval     time.Duration
	operations   []time.Time
	mu           sync.Mutex
}

// NewRateLimiter creates a new rate limiter
func NewRateLimiter(maxPerMinute int) *RateLimiter {
	return &RateLimiter{
		maxPerMinute: maxPerMinute,
		interval:     time.Minute / time.Duration(maxPerMinute),
		operations:   []time.Time{},
		mu:           sync.Mutex{},
	}
}

// Wait waits if needed to respect the rate limit
func (r *RateLimiter) Wait() {
	r.mu.Lock()
	defer r.mu.Unlock()

	now := time.Now()

	// Clean up old operations (older than 1 minute)
	var recent []time.Time
	for _, opTime := range r.operations {
		if now.Sub(opTime) <= time.Minute {
			recent = append(recent, opTime)
		}
	}
	r.operations = recent

	// Check if we need to wait
	if len(r.operations) >= r.maxPerMinute {
		// Need to wait until oldest operation + 1 minute
		waitUntil := r.operations[0].Add(time.Minute)
		waitTime := waitUntil.Sub(now)
		r.mu.Unlock()
		time.Sleep(waitTime)
		r.mu.Lock()
		now = time.Now()
	} else if len(r.operations) > 0 {
		// Ensure we're properly spacing operations
		lastOp := r.operations[len(r.operations)-1]
		timeSince := now.Sub(lastOp)
		if timeSince < r.interval {
			waitTime := r.interval - timeSince
			r.mu.Unlock()
			time.Sleep(waitTime)
			r.mu.Lock()
			now = time.Now()
		}
	}

	// Record this operation
	r.operations = append(r.operations, time.Now())
}

// Validator handles email validation
type Validator struct {
	config            Config
	tempFiles         []string
	mu                sync.Mutex
	ipRotator         *IPRotator
	rateLimiter       *RateLimiter
	domainThrottler   *DomainThrottler
	disposableDomains map[string]bool
}

// NewValidator creates a new validator with the given configuration
func NewValidator(config Config) *Validator {
	// Convert disposable domains to map for faster lookup
	disposableMap := make(map[string]bool)
	for domain, isDisposable := range config.DisposableDomains {
		disposableMap[domain] = isDisposable
	}

	return &Validator{
		config:            config,
		tempFiles:         []string{},
		ipRotator:         NewIPRotator(config.SourceIPs),
		rateLimiter:       NewRateLimiter(config.MaxPerMinute),
		domainThrottler:   NewDomainThrottler(5, 10), // 5 seconds default delay, max 10 per domain
		disposableDomains: disposableMap,
	}
}

// ValidateEmail validates a single email address
func (v *Validator) ValidateEmail(email string) (*ValidationResult, error) {
	// Apply rate limiting
	v.rateLimiter.Wait()

	// Validate email format
	if !v.isValidEmailFormat(email) {
		valid := false
		return &ValidationResult{
			Email:  email,
			Valid:  &valid,
			Status: "invalid",
			Reason: "Invalid email format",
		}, nil
	}

	// Extract domain
	parts := strings.Split(email, "@")
	if len(parts) != 2 {
		valid := false
		return &ValidationResult{
			Email:  email,
			Valid:  &valid,
			Status: "invalid",
			Reason: "Invalid email format",
		}, nil
	}
	domain := strings.TrimSpace(strings.ToLower(parts[1]))

	// Check for disposable email
	if v.disposableDomains[domain] {
		valid := false
		return &ValidationResult{
			Email:  email,
			Valid:  &valid,
			Status: "disposable",
			Reason: "Disposable email provider",
		}, nil
	}

	// Apply domain-specific throttling
	v.domainThrottler.WaitForDomain(domain)

	// Perform SMTP validation
	result, err := v.validateEmailSMTP(email, domain)
	if err != nil {
		return nil, err
	}

	return result, nil
}

// ValidateEmails validates a batch of emails
func (v *Validator) ValidateEmails(emails []string) (map[string]*ValidationResult, error) {
	if len(emails) == 0 {
		return map[string]*ValidationResult{}, nil
	}

	results := make(map[string]*ValidationResult)
	for _, email := range emails {
		result, err := v.ValidateEmail(email)
		if err != nil {
			// If there's an error, log it but continue with other emails
			log.Printf("Error validating %s: %v", email, err)
			results[email] = &ValidationResult{
				Email:  email,
				Status: "error",
				Reason: fmt.Sprintf("Validation error: %v", err),
			}
		} else {
			results[email] = result
		}
	}

	return results, nil
}

// validateEmailSMTP validates an email by checking SMTP
func (v *Validator) validateEmailSMTP(email, domain string) (*ValidationResult, error) {
	// Get MX records for the domain
	mxRecords, err := net.LookupMX(domain)
	if err != nil || len(mxRecords) == 0 {
		v.domainThrottler.ReportError(domain)
		valid := false
		return &ValidationResult{
			Email:  email,
			Valid:  &valid,
			Status: "invalid",
			Reason: "No MX records found",
		}, nil
	}

	// Sort MX records by preference (lowest first)
	// Convert to a simple array for easier randomization
	mxHosts := make([]string, len(mxRecords))
	for i, mx := range mxRecords {
		mxHosts[i] = mx.Host
	}

	// Try different tactics with exponential backoff between retries
	for attempt := 0; attempt < v.config.RetryLimit; attempt++ {
		// Add delay between retries
		if attempt > 0 {
			backoffTime := time.Duration(1<<uint(attempt)) * time.Second
			randomJitter := time.Duration(rand.Float64() * float64(time.Second))
			time.Sleep(backoffTime + randomJitter)
		}

		// Shuffle MX servers to distribute load and avoid patterns
		rand.Shuffle(len(mxHosts), func(i, j int) {
			mxHosts[i], mxHosts[j] = mxHosts[j], mxHosts[i]
		})

		for _, mxHost := range mxHosts {
			// Ensure the host name ends with a dot
			if !strings.HasSuffix(mxHost, ".") {
				mxHost += "."
			}
			// Remove the trailing dot for connection
			host := strings.TrimSuffix(mxHost, ".")

			// Get source IP if available
			sourceIP := v.ipRotator.GetNextIP()
			var sourceAddr *net.TCPAddr
			if sourceIP != "" {
				sourceAddr = &net.TCPAddr{
					IP: net.ParseIP(sourceIP),
				}
			}

			// Setup the dialer with the source address if specified
			dialer := &net.Dialer{
				Timeout:   time.Duration(v.config.Timeout) * time.Second,
				LocalAddr: sourceAddr,
			}

			// Connect to the SMTP server
			conn, err := dialer.Dial("tcp", fmt.Sprintf("%s:25", host))
			if err != nil {
				// Try next MX server
				continue
			}

			// Create SMTP client
			smtpClient, err := smtp.NewClient(conn, host)
			if err != nil {
				conn.Close()
				continue
			}

			defer smtpClient.Close()

			// Set random host name to avoid patterns
			hostChoices := []string{"example.com", "mail.com", "verifier.net", "checker.org"}
			clientName := hostChoices[rand.Intn(len(hostChoices))]

			// Try EHLO or HELO randomly
			var heloErr error
			if rand.Intn(2) == 0 {
				heloErr = smtpClient.Hello(clientName)
			} else {
				heloErr = smtpClient.Hello(clientName)
			}

			if heloErr != nil {
				continue
			}

			// Randomize sender for anti-pattern detection
			senderDomains := []string{"example.com", "test.net", "mail.org", "verify.com"}
			senderNames := []string{"verify", "test", "info", "contact"}
			randomSender := fmt.Sprintf("%s@%s",
				senderNames[rand.Intn(len(senderNames))],
				senderDomains[rand.Intn(len(senderDomains))])

			// Set sender
			err = smtpClient.Mail(randomSender)
			if err != nil {
				continue
			}

			// Check recipient
			err = smtpClient.Rcpt(email)
			if err != nil {
				// If rejected, the email is invalid
				v.domainThrottler.ReportSuccess(domain)
				valid := false
				return &ValidationResult{
					Email:  email,
					Valid:  &valid,
					Status: "invalid",
					Reason: "SMTP validation failed: recipient rejected",
				}, nil
			}

			// If we got here, the email is valid
			v.domainThrottler.ReportSuccess(domain)
			valid := true
			return &ValidationResult{
				Email:  email,
				Valid:  &valid,
				Status: "valid",
			}, nil
		}
	}

	// If all servers and retries failed
	v.domainThrottler.ReportError(domain)
	return &ValidationResult{
		Email:  email,
		Status: "unknown",
		Reason: "Could not determine validity after all retries",
	}, nil
}

// isValidEmailFormat checks if email format is valid using regex
func (v *Validator) isValidEmailFormat(email string) bool {
	pattern := `^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$`
	match, _ := regexp.MatchString(pattern, email)
	return match
}

// cleanupTempFiles removes temporary files that are older than 1 hour
func (v *Validator) cleanupTempFiles() {
	v.mu.Lock()
	defer v.mu.Unlock()

	oneHourAgo := time.Now().Add(-1 * time.Hour)
	remainingFiles := make([]string, 0)

	for _, file := range v.tempFiles {
		info, err := os.Stat(file)
		if err != nil {
			if !os.IsNotExist(err) {
				log.Printf("Error checking temp file %s: %v", file, err)
			}
			continue
		}

		// If file is older than 1 hour, delete it
		if info.ModTime().Before(oneHourAgo) {
			if err := os.Remove(file); err != nil {
				log.Printf("Error removing temp file %s: %v", file, err)
			}
		} else {
			remainingFiles = append(remainingFiles, file)
		}
	}

	v.tempFiles = remainingFiles
}

// min returns the minimum of two integers
func min(a, b int) int {
	if a < b {
		return a
	}
	return b
}

// max returns the maximum of two integers
func max(a, b int) int {
	if a > b {
		return a
	}
	return b
}

// EmailValidator handles validation of email addresses
type EmailValidator struct {
	config         Config
	ipIndex        int
	mutex          sync.Mutex
	lastUsed       map[string]time.Time      // Tracks last use time for each IP
	domainCounters map[string]*DomainCounter // Tracks rate limits per domain
}

// DomainCounter tracks rate limiting for a specific domain
type DomainCounter struct {
	count     int
	resetTime time.Time
	mutex     sync.Mutex
}

// Result represents the validation result for an email
type Result struct {
	Email      string // The email address
	Valid      bool   // Whether the email is valid
	Disposable bool   // Whether the email is from a disposable domain
	Reason     string // Reason for invalidity if not valid
}

// NewEmailValidator creates a new validator instance
func NewEmailValidator(config Config) *EmailValidator {
	if config.Timeout == 0 {
		config.Timeout = 10 * time.Second
	}

	return &EmailValidator{
		config:         config,
		ipIndex:        0,
		lastUsed:       make(map[string]time.Time),
		domainCounters: make(map[string]*DomainCounter),
	}
}

// LoadDisposableDomains loads disposable domain list from a file
func LoadDisposableDomains(filename string) (map[string]bool, error) {
	domains := make(map[string]bool)

	file, err := os.Open(filename)
	if err != nil {
		return domains, err
	}
	defer file.Close()

	scanner := bufio.NewScanner(file)
	for scanner.Scan() {
		domain := strings.TrimSpace(scanner.Text())
		// Skip empty lines and comments
		if domain != "" && !strings.HasPrefix(domain, "#") {
			domains[domain] = true
		}
	}

	if err := scanner.Err(); err != nil {
		return domains, err
	}

	return domains, nil
}

// LoadSourceIPs loads source IPs from a file
func LoadSourceIPs(filename string) ([]string, error) {
	var ips []string

	file, err := os.Open(filename)
	if err != nil {
		return ips, err
	}
	defer file.Close()

	scanner := bufio.NewScanner(file)
	for scanner.Scan() {
		ip := strings.TrimSpace(scanner.Text())
		// Skip empty lines and comments
		if ip != "" && !strings.HasPrefix(ip, "#") {
			ips = append(ips, ip)
		}
	}

	if err := scanner.Err(); err != nil {
		return ips, err
	}

	return ips, nil
}

// ValidateEmail checks if an email address is valid
func (v *EmailValidator) ValidateEmail(email string) Result {
	// Initialize result
	result := Result{
		Email: email,
		Valid: false,
	}

	// Basic format validation
	if !isValidFormat(email) {
		result.Reason = "Invalid email format"
		return result
	}

	// Split email into local part and domain
	parts := strings.Split(email, "@")
	if len(parts) != 2 {
		result.Reason = "Invalid email format"
		return result
	}

	domain := parts[1]

	// Check if it's a disposable domain
	if v.config.DisposableDomains[domain] {
		result.Disposable = true
	}

	// Apply rate limiting for the domain
	if !v.checkDomainRateLimit(domain) {
		result.Reason = "Domain rate limit exceeded"
		return result
	}

	// Get MX records
	mxRecords, err := net.LookupMX(domain)
	if err != nil || len(mxRecords) == 0 {
		result.Reason = "No MX records found"
		return result
	}

	// Try to validate against MX servers
	valid, reason := v.checkMailbox(email, mxRecords)
	result.Valid = valid
	result.Reason = reason

	return result
}

// checkDomainRateLimit checks if we've exceeded the rate limit for a domain
func (v *EmailValidator) checkDomainRateLimit(domain string) bool {
	v.mutex.Lock()
	counter, exists := v.domainCounters[domain]
	if !exists {
		counter = &DomainCounter{
			count:     0,
			resetTime: time.Now().Add(time.Minute),
		}
		v.domainCounters[domain] = counter
	}
	v.mutex.Unlock()

	counter.mutex.Lock()
	defer counter.mutex.Unlock()

	// Reset counter if a minute has passed
	if time.Now().After(counter.resetTime) {
		counter.count = 0
		counter.resetTime = time.Now().Add(time.Minute)
	}

	// Check if we've hit the limit
	if counter.count >= v.config.RateLimit {
		return false
	}

	// Increment the counter
	counter.count++
	return true
}

// getNextIP gets the next IP to use in a round-robin fashion with cooling period
func (v *EmailValidator) getNextIP() string {
	v.mutex.Lock()
	defer v.mutex.Unlock()

	if len(v.config.SourceIPs) == 0 {
		return ""
	}

	now := time.Now()
	cooldownPeriod := 60 * time.Second

	// Try to find an IP that hasn't been used recently
	for i := 0; i < len(v.config.SourceIPs); i++ {
		v.ipIndex = (v.ipIndex + 1) % len(v.config.SourceIPs)
		ip := v.config.SourceIPs[v.ipIndex]

		lastUsed, exists := v.lastUsed[ip]
		if !exists || now.Sub(lastUsed) > cooldownPeriod {
			v.lastUsed[ip] = now
			return ip
		}
	}

	// If all IPs are on cooldown, pick a random one
	v.ipIndex = rand.Intn(len(v.config.SourceIPs))
	ip := v.config.SourceIPs[v.ipIndex]
	v.lastUsed[ip] = now
	return ip
}

// checkMailbox attempts to verify if a mailbox exists
func (v *EmailValidator) checkMailbox(email string, mxRecords []*net.MX) (bool, string) {
	sourceIP := v.getNextIP()

	// Try each MX server until we get a definitive answer
	for _, mx := range mxRecords {
		server := mx.Host
		if !strings.HasSuffix(server, ".") {
			server += "."
		}

		// Remove the trailing dot
		server = server[:len(server)-1]

		// Connect to the SMTP server
		client, err := v.dialSMTP(server+":25", sourceIP)
		if err != nil {
			continue // Try the next MX server
		}

		defer client.Close()

		// SMTP handshake
		err = client.Hello("verification.test")
		if err != nil {
			continue
		}

		// Send MAIL FROM command
		err = client.Mail("verifier@example.com")
		if err != nil {
			continue
		}

		// Send RCPT TO command
		err = client.Rcpt(email)
		if err != nil {
			// If we get a definitive "no", return invalid
			return false, fmt.Sprintf("Mailbox check failed: %s", err)
		}

		// If we reach here, the email is likely valid
		return true, ""
	}

	// If we couldn't connect to any MX servers, we can't determine validity
	return false, "Could not connect to any mail server"
}

// dialSMTP connects to an SMTP server from a specific source IP
func (v *EmailValidator) dialSMTP(addr, sourceIP string) (*smtp.Client, error) {
	// If no source IP specified, use default dialer
	if sourceIP == "" {
		conn, err := net.DialTimeout("tcp", addr, v.config.Timeout)
		if err != nil {
			return nil, err
		}
		return smtp.NewClient(conn, addr)
	}

	// Create a dialer with the source IP
	dialer := &net.Dialer{
		Timeout: v.config.Timeout,
		LocalAddr: &net.TCPAddr{
			IP: net.ParseIP(sourceIP),
		},
	}

	conn, err := dialer.Dial("tcp", addr)
	if err != nil {
		return nil, err
	}

	return smtp.NewClient(conn, addr)
}

// isValidFormat checks if an email has a valid format
func isValidFormat(email string) bool {
	// Basic format check
	if !strings.Contains(email, "@") || strings.Count(email, "@") != 1 {
		return false
	}

	parts := strings.Split(email, "@")
	if len(parts) != 2 {
		return false
	}

	local, domain := parts[0], parts[1]

	// Local part checks
	if len(local) == 0 || len(local) > 64 {
		return false
	}

	// Domain checks
	if len(domain) == 0 || len(domain) > 255 || !strings.Contains(domain, ".") {
		return false
	}

	return true
}
