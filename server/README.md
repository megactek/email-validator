# Email Validator Server

A high-performance, scalable gRPC server for email validation written in Go.

## Features

- Direct SMTP mailbox validation
- IP rotation to prevent blocks and rate limits
- Disposable email detection
- High-throughput gRPC API with streaming support
- Real-time statistics

## Prerequisites

- Go 1.18 or higher
- Protocol Buffers compiler (protoc)

## Installation

1. Clone the repository:

   ```
   git clone https://github.com/megactek/email-validator.git
   cd email-validator/server
   ```

2. Generate protocol buffer code:

   ```
   ./generate_proto.sh
   ```

3. Build the server:

   ```
   go build -o email_validator main.go
   ```

## Configuration Files

### Source IPs (`source_ips.txt`)

A file containing source IP addresses to use for outbound connections, one per line:

```
192.168.1.1
192.168.1.2
```

### Disposable Domains (`disposable_domains.txt`)

A file containing disposable email domains, one per line:

```
10minutemail.com
mailinator.com
```

## Usage

Run the server with default settings:

```
./email_validator
```

With custom settings:

```
./email_validator \
  --port=50051 \
  --rate-limit=20 \
  --ips-file=source_ips.txt \
  --disposable-file=disposable_domains.txt
```

### Command-line Options

- `--port`: Server port (default: 50051)
- `--rate-limit`: Maximum checks per minute per domain (default: 20)
- `--ips-file`: Path to file containing source IPs
- `--disposable-file`: Path to file containing disposable domains

## API Endpoints

The server implements the following gRPC endpoints:

1. `ValidateEmail`: Validates a single email address
2. `ValidateEmails`: Validates a batch of email addresses
3. `ValidateEmailStream`: Bidirectional streaming for validating multiple emails
4. `GetStats`: Retrieves current validation statistics

## Performance Considerations

- The server employs IP rotation to prevent being blocked by mail servers
- Rate limiting is applied per mail domain to respect server limits
- The gRPC streaming API allows for efficient validation of large lists

## License

This project is licensed under the MIT License.
