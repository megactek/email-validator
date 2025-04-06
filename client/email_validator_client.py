#!/usr/bin/env python3
import os
import sys
import time
import argparse
import logging
import random
import grpc
import concurrent.futures
from typing import List, Dict, Set, Optional, Tuple
from pathlib import Path
from datetime import datetime
from tqdm import tqdm
from collections import deque
from threading import Lock, Event

# Import generated protocol buffer code
import email_validator_pb2
import email_validator_pb2_grpc

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    filename=f'email_validation_client_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log'
)
console = logging.StreamHandler()
console.setLevel(logging.INFO)
logging.getLogger('').addHandler(console)

class ValidationClient:
    """Client for email validation service."""
    
    def __init__(self, server_addresses: List[str], 
                 max_workers: int = 10,
                 batch_size: int = 100,
                 timeout: int = 30,
                 retry_limit: int = 3,
                 retry_delay: int = 5):
        self.server_addresses = server_addresses
        self.max_workers = max_workers
        self.batch_size = batch_size
        self.timeout = timeout
        self.retry_limit = retry_limit
        self.retry_delay = retry_delay
        
        # Track which server to use next for each thread
        self.server_index_lock = Lock()
        self.server_index = 0
        
        # Statistics
        self.stats_lock = Lock()
        self.stats = {
            'total': 0,
            'valid': 0,
            'invalid': 0,
            'unknown': 0,
            'error': 0,
            'disposable': 0,
            'retry_success': 0,
            'retry_failure': 0,
        }
        
        # Keep track of server performance
        self.server_performances = {addr: {'latency': deque(maxlen=100), 'errors': 0} 
                                   for addr in server_addresses}
        self.server_performances_lock = Lock()
        
        # Create server connections
        self.stubs = self._create_stubs()
        
        # Shutdown signal
        self.shutdown_event = Event()
        
    def _create_stubs(self) -> Dict[str, email_validator_pb2_grpc.EmailValidatorStub]:
        """Create gRPC stubs for all servers."""
        stubs = {}
        for addr in self.server_addresses:
            try:
                # Create an insecure channel
                channel = grpc.insecure_channel(addr)
                # Create a stub
                stub = email_validator_pb2_grpc.EmailValidatorStub(channel)
                stubs[addr] = stub
                logging.info(f"Connected to server at {addr}")
            except Exception as e:
                logging.error(f"Failed to connect to server at {addr}: {e}")
        
        if not stubs:
            raise ConnectionError("Could not connect to any validation servers")
            
        return stubs
        
    def _get_next_server(self) -> str:
        """Get the next server address to use, with basic load balancing."""
        with self.server_index_lock:
            server = self.server_addresses[self.server_index]
            self.server_index = (self.server_index + 1) % len(self.server_addresses)
            return server
            
    def _get_best_server(self) -> str:
        """Get the best performing server based on latency and error rate."""
        with self.server_performances_lock:
            best_server = None
            best_score = float('inf')
            
            for addr, perf in self.server_performances.items():
                # Calculate average latency
                latencies = list(perf['latency'])
                avg_latency = sum(latencies) / max(len(latencies), 1) if latencies else 10.0
                
                # Calculate error rate penalty
                error_penalty = perf['errors'] * 2
                
                # Lower score is better
                score = avg_latency + error_penalty
                
                if score < best_score:
                    best_score = score
                    best_server = addr
            
            # If we don't have performance data yet, just get the next server
            if best_server is None:
                best_server = self._get_next_server()
                
            return best_server
            
    def _record_performance(self, server: str, latency: float, error: bool = False):
        """Record server performance metrics."""
        with self.server_performances_lock:
            if server in self.server_performances:
                self.server_performances[server]['latency'].append(latency)
                if error:
                    self.server_performances[server]['errors'] += 1
    
    def validate_email(self, email: str) -> Dict:
        """Validate a single email using the validation service."""
        server = self._get_best_server()
        stub = self.stubs.get(server)
        
        if not stub:
            return {
                'email': email,
                'valid': None,
                'status': 'error',
                'reason': f"No connection to server {server}"
            }
            
        # Create a request
        request = email_validator_pb2.EmailRequest(email=email)
        
        # Try to validate with retries
        for attempt in range(self.retry_limit):
            if self.shutdown_event.is_set():
                return {
                    'email': email,
                    'valid': None,
                    'status': 'error',
                    'reason': "Client is shutting down"
                }
                
            try:
                start_time = time.time()
                response = stub.ValidateEmail(request, timeout=self.timeout)
                latency = time.time() - start_time
                
                # Record successful performance
                self._record_performance(server, latency)
                
                if attempt > 0:
                    with self.stats_lock:
                        self.stats['retry_success'] += 1
                
                # Map status from proto enum to string
                status_map = {
                    email_validator_pb2.ValidationStatus.UNKNOWN: 'unknown',
                    email_validator_pb2.ValidationStatus.VALID: 'valid',
                    email_validator_pb2.ValidationStatus.INVALID: 'invalid',
                    email_validator_pb2.ValidationStatus.ERROR: 'error',
                    email_validator_pb2.ValidationStatus.DISPOSABLE: 'disposable',
                }
                
                return {
                    'email': email,
                    'valid': response.status == email_validator_pb2.ValidationStatus.VALID,
                    'status': status_map.get(response.status, 'unknown'),
                    'reason': response.reason if response.reason else None
                }
                
            except grpc.RpcError as e:
                latency = time.time() - start_time
                self._record_performance(server, latency, error=True)
                
                # Log the error
                context = " ".join([f"{k}={v}" for k, v in e.trailing_metadata()])
                logging.warning(f"gRPC error validating {email} on {server}: {e.details()} {context}")
                
                # If we have more attempts, try another server after a delay
                if attempt < self.retry_limit - 1:
                    delay = self.retry_delay * (2 ** attempt) + random.uniform(0, 1)
                    time.sleep(delay)
                    server = self._get_best_server()  # Try a different server
                    stub = self.stubs.get(server)
                    if not stub:
                        continue
            except Exception as e:
                latency = time.time() - start_time
                self._record_performance(server, latency, error=True)
                
                logging.warning(f"Error validating {email} on {server}: {str(e)}")
                
                # If we have more attempts, try another server after a delay
                if attempt < self.retry_limit - 1:
                    delay = self.retry_delay * (2 ** attempt) + random.uniform(0, 1)
                    time.sleep(delay)
                    server = self._get_best_server()  # Try a different server
                    stub = self.stubs.get(server)
                    if not stub:
                        continue
        
        # If we get here, all attempts failed
        with self.stats_lock:
            self.stats['retry_failure'] += 1
            
        return {
            'email': email,
            'valid': None,
            'status': 'error',
            'reason': f"Failed after {self.retry_limit} attempts"
        }
    
    def validate_emails_streaming(self, emails: List[str], server: Optional[str] = None) -> List[Dict]:
        """Validate emails using bidirectional streaming."""
        if not emails:
            return []
            
        if server is None:
            server = self._get_best_server()
            
        stub = self.stubs.get(server)
        if not stub:
            return [{
                'email': email,
                'valid': None,
                'status': 'error',
                'reason': f"No connection to server {server}"
            } for email in emails]
        
        results = []
        try:
            # Start bidirectional streaming
            start_time = time.time()
            
            # Create a request generator function
            def request_iterator():
                for email in emails:
                    if self.shutdown_event.is_set():
                        return
                    yield email_validator_pb2.EmailRequest(email=email)
            
            # Pass the request iterator to the streaming call
            stream = stub.ValidateEmailStream(request_iterator(), timeout=self.timeout)
            
            # Receive all responses
            try:
                for response in stream:
                    status_map = {
                        email_validator_pb2.ValidationStatus.UNKNOWN: 'unknown',
                        email_validator_pb2.ValidationStatus.VALID: 'valid',
                        email_validator_pb2.ValidationStatus.INVALID: 'invalid',
                        email_validator_pb2.ValidationStatus.ERROR: 'error',
                        email_validator_pb2.ValidationStatus.DISPOSABLE: 'disposable',
                    }
                    
                    result = {
                        'email': response.email,
                        'valid': response.status == email_validator_pb2.ValidationStatus.VALID,
                        'status': status_map.get(response.status, 'unknown'),
                        'reason': response.reason if response.reason else None
                    }
                    results.append(result)
            except grpc.RpcError as e:
                # Log the error
                context = " ".join([f"{k}={v}" for k, v in e.trailing_metadata()])
                logging.warning(f"gRPC error in streaming response on {server}: {e.details()} {context}")
                raise e
                
            latency = time.time() - start_time
            avg_latency = latency / len(emails) if emails else 0
            self._record_performance(server, avg_latency)
            
            return results
            
        except Exception as e:
            latency = time.time() - start_time
            avg_latency = latency / len(emails) if emails else 0
            self._record_performance(server, avg_latency, error=True)
            
            logging.error(f"Error in streaming validation on {server}: {str(e)}")
            
            # Return error results for any emails that don't have results yet
            processed_emails = set(r['email'] for r in results)
            missing_emails = [e for e in emails if e not in processed_emails]
            
            for email in missing_emails:
                results.append({
                    'email': email,
                    'valid': None,
                    'status': 'error',
                    'reason': f"Stream error: {str(e)}"
                })
                
            return results
    
    def process_batch(self, emails: List[str]) -> List[Dict]:
        """Process a batch of emails using streaming."""
        # Try each server in order
        for server_idx in range(len(self.server_addresses)):
            server = self.server_addresses[(self.server_index + server_idx) % len(self.server_addresses)]
            
            try:
                results = self.validate_emails_streaming(emails, server)
                
                # If we got here, the batch was successful
                return results
            except Exception as e:
                logging.warning(f"Batch processing failed on server {server}: {str(e)}")
                
                # If this was the last server, give up
                if server_idx == len(self.server_addresses) - 1:
                    return [{
                        'email': email,
                        'valid': None,
                        'status': 'error',
                        'reason': f"All servers failed: {str(e)}"
                    } for email in emails]
                    
                # Otherwise, try the next server after a short delay
                time.sleep(1)
    
    def _worker(self, emails: List[str]) -> List[Dict]:
        """Process emails in a worker thread."""
        # Process in batch_size chunks
        results = []
        for i in range(0, len(emails), self.batch_size):
            if self.shutdown_event.is_set():
                break
                
            batch = emails[i:i+self.batch_size]
            batch_results = self.process_batch(batch)
            results.extend(batch_results)
            
            # Update stats
            with self.stats_lock:
                self.stats['total'] += len(batch_results)
                for result in batch_results:
                    status = result.get('status', 'unknown')
                    if status in self.stats:
                        self.stats[status] += 1
        
        return results
    
    def process_file(self, input_file: str, output_prefix: str, 
                    resume: bool = False, checkpoint_interval: int = 1000) -> None:
        """Process a text file with email addresses (one per line)."""
        start_time = time.time()
        processed = 0
        checkpoint_time = start_time
        
        # Create output directory if needed
        output_dir = os.path.dirname(output_prefix)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir)
        
        # Output files
        valid_file = f"{output_prefix}_valid.txt"
        invalid_file = f"{output_prefix}_invalid.txt"
        disposable_file = f"{output_prefix}_disposable.txt"
        unknown_file = f"{output_prefix}_unknown.txt"
        
        # Track which emails have been processed for resuming
        processed_emails = set()
        
        # If resuming, read already processed emails
        if resume:
            for filename in [valid_file, invalid_file, disposable_file, unknown_file]:
                if os.path.exists(filename):
                    with open(filename, 'r', encoding='utf-8') as f:
                        for line in f:
                            email = line.strip()
                            if email:
                                processed_emails.add(email)
            
            logging.info(f"Resuming with {len(processed_emails)} already processed emails")
        
        try:
            # Read emails from input file
            emails_to_process = []
            with open(input_file, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    email = line.strip()
                    if email and (not resume or email not in processed_emails):
                        emails_to_process.append(email)
            
            total_emails = len(emails_to_process)
            logging.info(f"Processing {total_emails} emails from {input_file}")
            
            # Open output files
            with open(valid_file, 'a' if resume else 'w', encoding='utf-8') as f_valid, \
                 open(invalid_file, 'a' if resume else 'w', encoding='utf-8') as f_invalid, \
                 open(disposable_file, 'a' if resume else 'w', encoding='utf-8') as f_disposable, \
                 open(unknown_file, 'a' if resume else 'w', encoding='utf-8') as f_unknown:
                
                # Process in chunks to allow for better progress reporting
                chunk_size = min(1000, total_emails)
                with tqdm(total=total_emails, desc="Validating emails") as pbar:
                    for i in range(0, total_emails, chunk_size):
                        if self.shutdown_event.is_set():
                            break
                            
                        chunk = emails_to_process[i:i+chunk_size]
                        
                        # Split into batches for parallel processing
                        batches = []
                        batch_size = max(1, min(self.batch_size, chunk_size // self.max_workers))
                        for j in range(0, len(chunk), batch_size):
                            batches.append(chunk[j:j+batch_size])
                        
                        # Process batches in parallel
                        results = []
                        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                            futures = [executor.submit(self._worker, batch) for batch in batches]
                            for future in concurrent.futures.as_completed(futures):
                                if self.shutdown_event.is_set():
                                    for f in futures:
                                        f.cancel()
                                    break
                                    
                                try:
                                    batch_results = future.result()
                                    results.extend(batch_results)
                                    pbar.update(len(batch_results))
                                except Exception as e:
                                    logging.error(f"Worker thread error: {str(e)}")
                        
                        # Write results to output files
                        for result in results:
                            email = result.get('email', '')
                            status = result.get('status', 'unknown')
                            
                            if status == 'valid':
                                f_valid.write(f"{email}\n")
                            elif status == 'invalid':
                                f_invalid.write(f"{email}\n")
                            elif status == 'disposable':
                                f_disposable.write(f"{email}\n")
                            else:  # unknown or error
                                f_unknown.write(f"{email}\n")
                        
                        # Flush files to ensure data is written
                        f_valid.flush()
                        f_invalid.flush()
                        f_disposable.flush()
                        f_unknown.flush()
                        
                        processed += len(results)
                        
                        # Log progress at checkpoints
                        if processed % checkpoint_interval == 0:
                            now = time.time()
                            elapsed_total = now - start_time
                            elapsed_checkpoint = now - checkpoint_time
                            checkpoint_time = now
                            
                            rate_total = processed / elapsed_total if elapsed_total > 0 else 0
                            rate_checkpoint = checkpoint_interval / elapsed_checkpoint if elapsed_checkpoint > 0 else 0
                            
                            # Calculate estimated time remaining
                            remaining_emails = total_emails - processed
                            est_time_sec = remaining_emails / rate_checkpoint if rate_checkpoint > 0 else 0
                            hours, remainder = divmod(est_time_sec, 3600)
                            minutes, seconds = divmod(remainder, 60)
                            est_remaining = f"{int(hours)}h {int(minutes)}m"
                            
                            # Log progress
                            with self.stats_lock:
                                logging.info(f"Processed {processed}/{total_emails} emails. "
                                           f"Current rate: {rate_checkpoint:.2f}/sec. "
                                           f"Avg rate: {rate_total:.2f}/sec. "
                                           f"Est. remaining: {est_remaining}. "
                                           f"Results: valid={self.stats['valid']}, "
                                           f"invalid={self.stats['invalid']}, "
                                           f"disposable={self.stats['disposable']}, "
                                           f"unknown={self.stats['unknown']}, "
                                           f"error={self.stats['error']}, "
                                           f"retry_success={self.stats['retry_success']}, "
                                           f"retry_failure={self.stats['retry_failure']}")
        
            # Final stats
            elapsed = time.time() - start_time
            rate = processed / elapsed if elapsed > 0 else 0
            
            with self.stats_lock:
                logging.info(f"Completed! Processed {processed} emails in {elapsed:.2f} seconds. "
                            f"Rate: {rate:.2f} emails/sec. Final results: {self.stats}")
                            
        except KeyboardInterrupt:
            logging.info("Process interrupted by user.")
            self.shutdown_event.set()
        except Exception as e:
            logging.error(f"Error processing file: {str(e)}")
            self.shutdown_event.set()
            raise
    
    def shutdown(self):
        """Signal client to shut down gracefully."""
        self.shutdown_event.set()

def main():
    """Main function to run the client."""
    parser = argparse.ArgumentParser(description='Email validation client')
    parser.add_argument('input_file', help='Input text file with one email per line')
    parser.add_argument('output_prefix', help='Prefix for output files')
    parser.add_argument('--servers', required=True, help='Comma-separated list of server addresses (host:port)')
    parser.add_argument('--batch-size', type=int, default=100, help='Batch size for streaming')
    parser.add_argument('--max-workers', type=int, default=10, help='Maximum worker threads')
    parser.add_argument('--timeout', type=int, default=30, help='gRPC timeout in seconds')
    parser.add_argument('--retry-limit', type=int, default=3, help='Number of retries per operation')
    parser.add_argument('--checkpoint', type=int, default=1000, help='How often to log progress')
    parser.add_argument('--resume', action='store_true', help='Resume from last run')
    
    args = parser.parse_args()
    
    # Parse server addresses
    server_addresses = [addr.strip() for addr in args.servers.split(',') if addr.strip()]
    if not server_addresses:
        logging.error("No valid server addresses provided")
        sys.exit(1)
        
    logging.info(f"Using servers: {server_addresses}")
    
    # Create client
    client = ValidationClient(
        server_addresses=server_addresses,
        max_workers=args.max_workers,
        batch_size=args.batch_size,
        timeout=args.timeout,
        retry_limit=args.retry_limit
    )
    
    try:
        # Process the file
        client.process_file(
            input_file=args.input_file,
            output_prefix=args.output_prefix,
            resume=args.resume,
            checkpoint_interval=args.checkpoint
        )
    except KeyboardInterrupt:
        print("\nShutting down gracefully. Please wait...")
        client.shutdown()
    except Exception as e:
        logging.error(f"Fatal error: {str(e)}")
        client.shutdown()
        sys.exit(1)

if __name__ == "__main__":
    main() 