import socket
import smtplib
import dns.resolver
import concurrent.futures
import time
import random
import logging
import re
import os
from typing import List, Dict, Optional, Set
from datetime import datetime
from collections import deque
from threading import Lock, Event
import ipaddress

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    filename=f'email_validation_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log'
)
console = logging.StreamHandler()
console.setLevel(logging.INFO)
logging.getLogger('').addHandler(console)

class SmartRateLimiter:
    """Rate limiter that evenly distributes operations over a minute"""
    def __init__(self, max_per_minute: int):
        self.max_per_minute = max_per_minute
        self.interval = 60.0 / max_per_minute if max_per_minute > 0 else 3.0
        self.operation_times = deque(maxlen=max_per_minute)
        self.lock = Lock()
        
    def wait_if_needed(self):
        """Wait to evenly distribute operations"""
        with self.lock:
            now = time.time()
            
            # If we have previous operations, ensure proper spacing
            if self.operation_times:
                last_op_time = self.operation_times[-1]
                time_since_last = now - last_op_time
                
                # If not enough time has passed since the last operation
                if time_since_last < self.interval:
                    sleep_time = self.interval - time_since_last
                    time.sleep(sleep_time)
            
            # Record this operation time after any waiting
            self.operation_times.append(time.time())

class DomainThrottler:
    """Manages domain-specific rate limiting to avoid triggering anti-spam measures"""
    def __init__(self, default_delay=5, max_per_domain=10):
        self.domain_access = {}  # Domain -> list of access times
        self.domain_errors = {}  # Domain -> consecutive error count
        self.lock = Lock()
        self.default_delay = default_delay
        self.max_per_domain = max_per_domain
        
    def wait_for_domain(self, domain):
        """Wait if necessary before accessing a domain"""
        with self.lock:
            now = time.time()
            
            # Initialize domain if not seen before
            if domain not in self.domain_access:
                self.domain_access[domain] = deque(maxlen=self.max_per_domain)
                self.domain_errors[domain] = 0
            
            # Remove access times older than 60 seconds
            while self.domain_access[domain] and now - self.domain_access[domain][0] > 60:
                self.domain_access[domain].popleft()
                
            # Calculate delay based on error count and recent accesses
            error_count = self.domain_errors[domain]
            recent_access_count = len(self.domain_access[domain])
            
            # Exponential backoff based on errors
            delay = self.default_delay * (2 ** min(error_count, 5))
            
            # Add additional delay if we've accessed this domain many times recently
            if recent_access_count >= self.max_per_domain / 2:
                delay += recent_access_count
                
            # If we have recent accesses, ensure minimum time between them
            if self.domain_access[domain]:
                last_access = self.domain_access[domain][-1]
                time_since_last = now - last_access
                if time_since_last < delay:
                    time.sleep(delay - time_since_last)
            
            # Record this access
            self.domain_access[domain].append(time.time())
    
    def report_success(self, domain):
        """Report successful domain access"""
        with self.lock:
            if domain in self.domain_errors:
                self.domain_errors[domain] = max(0, self.domain_errors[domain] - 1)
    
    def report_error(self, domain):
        """Report domain access error to increase backoff"""
        with self.lock:
            if domain in self.domain_errors:
                self.domain_errors[domain] += 1

class IPRotator:
    """Rotates between multiple source IP addresses if available"""
    def __init__(self, ip_file=None):
        self.ips = []
        self.current_index = 0
        self.lock = Lock()
        
        # Try to load IPs from file if provided
        if ip_file and os.path.exists(ip_file):
            try:
                with open(ip_file, 'r') as f:
                    for line in f:
                        ip = line.strip()
                        try:
                            ipaddress.ip_address(ip)  # Validate IP
                            self.ips.append(ip)
                        except ValueError:
                            logging.warning(f"Invalid IP address: {ip}")
            except Exception as e:
                logging.error(f"Error loading IP addresses: {str(e)}")
        
        if not self.ips:
            logging.info("No valid source IPs found, will use system default")
    
    def get_next_ip(self):
        """Get the next IP in the rotation"""
        if not self.ips:
            return None
            
        with self.lock:
            ip = self.ips[self.current_index]
            self.current_index = (self.current_index + 1) % len(self.ips)
            return ip

class EmailValidator:
    def __init__(self, timeout: int = 10, max_workers: int = 5, retry_limit: int = 3, 
                 max_per_minute: int = 20, ip_file=None):
        self.timeout = timeout
        self.max_workers = max_workers
        self.retry_limit = retry_limit
        self.rate_limiter = SmartRateLimiter(max_per_minute)
        self.domain_throttler = DomainThrottler()
        self.ip_rotator = IPRotator(ip_file)
        self.shutdown_event = Event()
        
        self.results = {
            'valid': 0,
            'invalid': 0,
            'unknown': 0,
            'error': 0,
            'disposable': 0
        }
        self.results_lock = Lock()
        
        # Common disposable email domains
        self.disposable_domains = self._load_disposable_domains()
        
        # Track previously verified domains to avoid redundant MX lookups
        self.domain_cache = {}
        self.domain_cache_lock = Lock()
        
    def _load_disposable_domains(self):
        """Load list of known disposable email domains"""
        domains = set([
            'mailinator.com', 'temp-mail.org', 'guerrillamail.com', 'tempmail.com',
            'fakeinbox.com', '10minutemail.com', 'yopmail.com', 'dispostable.com',
            'mailnesia.com', 'mailcatch.com', 'trashmail.com', 'sharklasers.com',
            'tempinbox.com', 'tempmailaddress.com', 'throwawaymail.com', 'getnada.com',
            'temp-mail.io', 'spambox.us', 'tempr.email', 'trash-mail.com',
            'tempmail.net', 'emailondeck.com', 'tempmailer.com', 'maildrop.cc',
        ])
        
        # Try to load additional domains from file
        try:
            if os.path.exists('disposable_domains.txt'):
                with open('disposable_domains.txt', 'r') as f:
                    for line in f:
                        domain = line.strip().lower()
                        if domain and not domain.startswith('#'):
                            domains.add(domain)
        except Exception as e:
            logging.warning(f"Error loading disposable domains file: {str(e)}")
            
        return domains
        
    def extract_domain(self, email: str) -> Optional[str]:
        """Extract the domain part from an email address."""
        try:
            return email.split('@')[1].strip().lower()
        except (IndexError, AttributeError):
            return None
    
    def is_valid_email_format(self, email: str) -> bool:
        """Check if email format is valid using regex"""
        # Simple but effective regex for most valid emails
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return bool(re.match(pattern, email))
            
    def get_mx_record(self, domain: str) -> List[str]:
        """Get MX records for a domain with caching."""
        with self.domain_cache_lock:
            if domain in self.domain_cache:
                return self.domain_cache[domain]
        
        try:
            mx_records = dns.resolver.resolve(domain, 'MX')
            # Sort MX records by preference (lowest first)
            mx_hosts = sorted([(rec.preference, rec.exchange.to_text().rstrip('.')) 
                               for rec in mx_records])
            result = [host for _, host in mx_hosts]
            
            # Cache the result
            with self.domain_cache_lock:
                self.domain_cache[domain] = result
                
            return result
        except Exception as e:
            logging.debug(f"Failed to get MX record for {domain}: {str(e)}")
            
            # Cache empty result to avoid repeated lookups
            with self.domain_cache_lock:
                self.domain_cache[domain] = []
                
            return []
    
    def verify_email(self, email: str, sender_email: str = 'verify@example.com') -> Dict:
        """Verify a single email address using multiple methods."""
        # Check for shutdown signal
        if self.shutdown_event.is_set():
            return {
                'email': email,
                'valid': None,
                'reason': 'Validation process shutting down',
                'status': 'unknown'
            }
        
        # Wait according to rate limit
        self.rate_limiter.wait_if_needed()
        
        # Basic format check
        if not email or '@' not in email or not self.is_valid_email_format(email):
            return {
                'email': email,
                'valid': False,
                'reason': 'Invalid email format',
                'status': 'invalid'
            }
        
        email = email.lower().strip()
        domain = self.extract_domain(email)
        
        if not domain:
            return {
                'email': email,
                'valid': False,
                'reason': 'Invalid domain',
                'status': 'invalid'
            }
        
        # Check for disposable email
        if domain in self.disposable_domains:
            return {
                'email': email,
                'valid': False,
                'reason': 'Disposable email provider',
                'status': 'disposable'
            }
            
        # Apply domain-specific throttling
        self.domain_throttler.wait_for_domain(domain)
        
        # Get MX records
        mx_hosts = self.get_mx_record(domain)
        
        if not mx_hosts:
            return {
                'email': email,
                'valid': False,
                'reason': 'No MX records found',
                'status': 'invalid'
            }
        
        # Try different tactics with exponential backoff between retries
        for attempt in range(self.retry_limit):
            if self.shutdown_event.is_set():
                return {
                    'email': email,
                    'valid': None,
                    'reason': 'Validation process shutting down',
                    'status': 'unknown'
                }
                
            # Add delay between retries
            if attempt > 0:
                backoff_time = 2 ** attempt + random.uniform(0, 1)
                time.sleep(backoff_time)
            
            # Shuffle MX servers to distribute load and avoid patterns
            mx_servers = mx_hosts.copy()
            random.shuffle(mx_servers)
            
            for mx_host in mx_servers:
                try:
                    # Get source IP if available
                    source_ip = self.ip_rotator.get_next_ip()
                    source_address = (source_ip, 0) if source_ip else None
                    
                    with smtplib.SMTP(mx_host, 25, timeout=self.timeout, 
                                     source_address=source_address) as smtp:
                        smtp.set_debuglevel(0)
                        
                        # Identify with different host names to avoid patterns
                        host_choices = ['example.com', 'mail.com', 'verifier.net', 'checker.org']
                        host = random.choice(host_choices)
                        
                        # Try HELO or EHLO randomly
                        if random.choice([True, False]):
                            smtp.ehlo(host)
                        else:
                            smtp.helo(host)
                        
                        # Randomize sender within allowed patterns
                        sender_domains = ['example.com', 'test.net', 'mail.org', 'verify.com']
                        sender_names = ['verify', 'test', 'info', 'contact']
                        random_sender = f"{random.choice(sender_names)}@{random.choice(sender_domains)}"
                        
                        smtp.mail(random_sender)
                        code, message = smtp.rcpt(email)
                        
                        # Valid response
                        if code == 250:
                            self.domain_throttler.report_success(domain)
                            return {
                                'email': email,
                                'valid': True,
                                'status': 'valid'
                            }
                        # Soft failures (could be anti-harvesting)
                        elif code in [251, 252, 253]:
                            self.domain_throttler.report_success(domain)
                            return {
                                'email': email,
                                'valid': True,  # Assume valid with caveat
                                'reason': f"Server accepted with code {code}",
                                'status': 'valid'
                            }
                        # Hard failures
                        else:
                            self.domain_throttler.report_error(domain)
                            return {
                                'email': email,
                                'valid': False,
                                'reason': f"SMTP check failed with code {code}",
                                'status': 'invalid'
                            }
                            
                except (socket.timeout, socket.gaierror, smtplib.SMTPServerDisconnected, 
                        smtplib.SMTPResponseException, ConnectionRefusedError) as e:
                    # Server-specific error, try next server
                    continue
                    
                except Exception as e:
                    # Log the specific error for debugging
                    logging.debug(f"Error checking {email}: {str(e)}")
                    
                    # Check for common block indicators
                    error_str = str(e).lower()
                    if any(term in error_str for term in ['block', 'reject', 'denied', 'blacklist']):
                        self.domain_throttler.report_error(domain)
                        logging.warning(f"Possible blocking detected for domain {domain}")
                        
                        # Longer backoff for this domain
                        time.sleep(10 + random.uniform(0, 5))
                    
                    # Try next server
                    continue
        
        # If we get here, all MX servers and retries failed
        self.domain_throttler.report_error(domain)
        return {
            'email': email,
            'valid': None,
            'reason': 'Could not determine validity',
            'status': 'unknown'
        }
    
    def secondary_verification(self, result: Dict) -> Dict:
        """Apply secondary verification methods for indeterminate results"""
        # If already valid or invalid, return as is
        if result['status'] in ['valid', 'invalid', 'disposable']:
            return result
            
        email = result['email']
        domain = self.extract_domain(email)
        
        # Check for common username patterns that are likely valid
        username = email.split('@')[0]
        common_valid_patterns = [
            r'^[a-z][a-z0-9]{2,}$',                     # Common format like jsmith
            r'^[a-z]+\.[a-z]+$',                        # first.last
            r'^[a-z]\.?[a-z]+$',                        # j.smith or jsmith
            r'^[a-z]{1,3}\.[a-z]{3,}$',                 # john.smith or j.smith
        ]
        
        for pattern in common_valid_patterns:
            if re.match(pattern, username):
                result['valid'] = True
                result['status'] = 'valid'
                result['reason'] = 'Determined valid by username pattern analysis'
                return result
        
        # Check for common invalid usernames
        invalid_patterns = [
            r'^test[0-9]*$',                            # test, test1, etc.
            r'^[a-z]{1,2}$',                            # Single letter or two letters
            r'^admin$|^support$|^info$',                # Generic names often rejected
            r'^[0-9]+$',                                # Only numbers
        ]
        
        for pattern in invalid_patterns:
            if re.match(pattern, username):
                result['valid'] = False
                result['status'] = 'invalid'
                result['reason'] = 'Determined invalid by username pattern analysis'
                return result
        
        # If still unknown, leave as unknown
        return result
        
    def validate_batch(self, emails: List[str], sender_email: str = 'verify@example.com') -> List[Dict]:
        """Validate a batch of emails concurrently."""
        results = []
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_email = {executor.submit(self.verify_email, email, sender_email): email 
                              for email in emails}
            
            # Process as they complete
            for future in concurrent.futures.as_completed(future_to_email):
                if self.shutdown_event.is_set():
                    break
                    
                email = future_to_email[future]
                try:
                    result = future.result()
                    
                    # Apply secondary verification for unknown results
                    if result['status'] == 'unknown':
                        result = self.secondary_verification(result)
                    
                    results.append(result)
                    
                    # Update counters thread-safely
                    status = result.get('status', 'unknown')
                    with self.results_lock:
                        if status in self.results:
                            self.results[status] += 1
                        
                except Exception as e:
                    results.append({
                        'email': email,
                        'valid': None,
                        'reason': f"Unexpected error: {str(e)}",
                        'status': 'error'
                    })
                    with self.results_lock:
                        self.results['error'] += 1
                    
        return results
    
    def shutdown(self):
        """Signal threads to shut down gracefully"""
        self.shutdown_event.set()
        
    def process_file(self, input_file: str, output_file: str, batch_size: int = 20,
                    sender_email: str = 'verify@example.com', checkpoint_interval: int = 1000) -> None:
        """Process a text file with email addresses (one per line)."""
        start_time = time.time()
        processed = 0
        checkpoint_time = start_time
        
        try:
            # Create output directories if needed
            output_dir = os.path.dirname(output_file)
            if output_dir and not os.path.exists(output_dir):
                os.makedirs(output_dir)
            
            # Track already seen emails to avoid duplicates
            seen_emails = set()
            
            # Open input file
            with open(input_file, 'r', encoding='utf-8', errors='ignore') as f:
                # Open output files for different categories
                with open(output_file, 'w', encoding='utf-8') as out_valid, \
                     open(output_file.replace('.txt', '_invalid.txt'), 'w', encoding='utf-8') as out_invalid, \
                     open(output_file.replace('.txt', '_unknown.txt'), 'w', encoding='utf-8') as out_unknown:
                    
                    batch = []
                    for line in f:
                        if self.shutdown_event.is_set():
                            logging.info("Shutdown signal received. Stopping processing.")
                            break
                            
                        email = line.strip()
                        if email and email not in seen_emails:
                            seen_emails.add(email)
                            batch.append(email)
                            
                            if len(batch) >= batch_size:
                                results = self.validate_batch(batch, sender_email)
                                
                                # Write to appropriate output files
                                for result in results:
                                    status = result.get('status')
                                    email = result.get('email', '')
                                    
                                    if status == 'valid':
                                        out_valid.write(f"{email}\n")
                                        out_valid.flush()
                                    elif status in ['invalid', 'disposable']:
                                        out_invalid.write(f"{email}\n")
                                        out_invalid.flush()
                                    else:  # unknown or error
                                        out_unknown.write(f"{email}\n")
                                        out_unknown.flush()
                                
                                processed += len(batch)
                                batch = []
                                
                                # Log progress at checkpoints
                                if processed % checkpoint_interval == 0:
                                    now = time.time()
                                    elapsed_total = now - start_time
                                    elapsed_checkpoint = now - checkpoint_time
                                    checkpoint_time = now
                                    
                                    rate_total = processed / elapsed_total if elapsed_total > 0 else 0
                                    rate_checkpoint = checkpoint_interval / elapsed_checkpoint if elapsed_checkpoint > 0 else 0
                                    
                                    est_remaining = "N/A"
                                    if rate_checkpoint > 0 and hasattr(f, 'tell') and hasattr(f, 'seek'):
                                        try:
                                            current_pos = f.tell()
                                            f.seek(0, os.SEEK_END)
                                            total_size = f.tell()
                                            f.seek(current_pos, os.SEEK_SET)
                                            
                                            # Rough estimate of remaining emails
                                            remaining_portion = (total_size - current_pos) / total_size
                                            remaining_emails = processed * remaining_portion
                                            est_time_sec = remaining_emails / rate_checkpoint
                                            
                                            hours, remainder = divmod(est_time_sec, 3600)
                                            minutes, seconds = divmod(remainder, 60)
                                            est_remaining = f"{int(hours)}h {int(minutes)}m"
                                        except:
                                            pass
                                    
                                    logging.info(f"Processed {processed} emails. "
                                                f"Current rate: {rate_checkpoint:.2f}/sec. "
                                                f"Avg rate: {rate_total:.2f}/sec. "
                                                f"Est. remaining: {est_remaining}. "
                                                f"Results: valid={self.results['valid']}, "
                                                f"invalid={self.results['invalid']}, "
                                                f"disposable={self.results['disposable']}, "
                                                f"unknown={self.results['unknown']}, "
                                                f"error={self.results['error']}")
                    
                    # Process remaining emails
                    if batch:
                        results = self.validate_batch(batch, sender_email)
                        for result in results:
                            status = result.get('status')
                            email = result.get('email', '')
                            
                            if status == 'valid':
                                out_valid.write(f"{email}\n")
                            elif status in ['invalid', 'disposable']:
                                out_invalid.write(f"{email}\n")
                            else:  # unknown or error
                                out_unknown.write(f"{email}\n")
                                
                        processed += len(batch)
            
            # Final stats
            elapsed = time.time() - start_time
            rate = processed / elapsed if elapsed > 0 else 0
            logging.info(f"Completed! Processed {processed} emails in {elapsed:.2f} seconds. "
                        f"Rate: {rate:.2f} emails/sec. Final results: {self.results}")
                        
        except KeyboardInterrupt:
            logging.info("Process interrupted by user.")
            self.shutdown()
        except Exception as e:
            logging.error(f"Error processing file: {str(e)}")
            raise

def main():
    """Main function to run the validator."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Validate email addresses using SMTP (text files)')
    parser.add_argument('input_file', help='Input text file with one email per line')
    parser.add_argument('output_file', help='Output text file for valid emails')
    parser.add_argument('--batch-size', type=int, default=20, help='Batch size for processing')
    parser.add_argument('--timeout', type=int, default=10, help='SMTP connection timeout')
    parser.add_argument('--max-workers', type=int, default=5, help='Maximum concurrent workers')
    parser.add_argument('--retry-limit', type=int, default=3, help='Number of retries per email')
    parser.add_argument('--sender-email', default='verify@example.com',
                      help='Email to use in MAIL FROM command')
    parser.add_argument('--max-per-minute', type=int, default=20,
                      help='Maximum number of SMTP checks per minute')
    parser.add_argument('--checkpoint', type=int, default=1000,
                      help='How often to log progress (number of emails)')
    parser.add_argument('--ip-file', 
                      help='File containing source IP addresses to rotate through')
    
    args = parser.parse_args()
    
    validator = EmailValidator(
        timeout=args.timeout,
        max_workers=args.max_workers,
        retry_limit=args.retry_limit,
        max_per_minute=args.max_per_minute,
        ip_file=args.ip_file
    )
    
    try:
        validator.process_file(
            input_file=args.input_file,
            output_file=args.output_file,
            batch_size=args.batch_size,
            sender_email=args.sender_email,
            checkpoint_interval=args.checkpoint
        )
    except KeyboardInterrupt:
        print("\nShutting down gracefully. Please wait...")
        validator.shutdown()
        
if __name__ == "__main__":
    main()