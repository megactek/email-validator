# High-Volume Email Validation System

A distributed, high-performance system for validating millions of email addresses quickly and efficiently.

## Overview

This system provides a scalable solution for validating large lists of email addresses, capable of handling over 10 million emails across multiple servers. It performs real mailbox validation by directly connecting to mail servers and checking if the mailbox exists.

## Components

1. **Go gRPC Server**: A high-performance server written in Go that performs direct email validation by connecting to mail servers
2. **Python Client**: A client that streams emails to the server and processes results
3. **Helper Scripts**: Tools for distributed processing, result aggregation, and process management

## Key Features

- Direct mailbox validation with SMTP checks
- IP rotation to prevent blocks and rate limits
- Disposable email detection
- Distributed processing across multiple servers
- Stream-based architecture for handling large datasets
- Advanced error handling and retry mechanisms
- Real-time statistics and progress reporting

## Architecture

The system follows a client-server architecture using gRPC:

1. **Server**: Implements email validation logic with:

   - Real-time SMTP checks
   - IP rotation from a pool of source IPs
   - Rate limiting to prevent blocks
   - Disposable domain detection

2. **Client**:
   - Streams emails to the server
   - Processes validation results
   - Writes outputs to categorized files (valid, invalid, disposable, unknown)

## Workflow

1. Split a large email list across multiple servers
2. Each server processes its chunk with multiple worker threads
3. Results are saved into separate output files
4. A merge script combines results and generates statistics

## Performance

- Processes 500,000+ emails per hour per server
- Uses IP rotation to handle mail server rate limits
- Supports multiple parallel connections
- Implements backoff strategies for optimal throughput

## Usage

### Server

```
cd server
make proto
make build
./email_validator --ips-file=source_ips.txt --disposable-file=disposable_domains.txt
```

### Client

```
cd client
./generate_proto.sh
python email_validator_client.py input.txt output_prefix --servers=server1:50051
```

### Distributed Processing

```
./run_distributed.sh input.txt output_dir server1:50051,server2:50051,server3:50051
```

### Merging Results

```
./merge_results.sh output_dir merged_results
```

## License

MIT
