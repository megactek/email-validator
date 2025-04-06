# Email Validation Client

A Python client for validating large lists of email addresses using the email validation gRPC service.

## Features

- Distributed validation across multiple validation servers
- Bidirectional streaming for efficient processing
- Intelligent load balancing based on server performance
- Resume functionality to continue interrupted validations
- Progress tracking with estimated completion time
- Parallel processing with multiple worker threads

## Prerequisites

- Python 3.6+
- Required Python packages (see requirements.txt)

## Installation

1. Clone the repository:

   ```
   git clone https://github.com/megactek/email-validator.git
   cd email-validator/client
   ```

2. Install the required packages:

   ```
   pip install -r requirements.txt
   ```

3. Generate the Protocol Buffer code:
   ```
   python -m grpc_tools.protoc -I. --python_out=. --grpc_python_out=. email_validator.proto
   ```

## Usage

Run the client:

```
python email_validator_client.py input_file output_prefix --servers server1:port1,server2:port2,server3:port3 [options]
```

### Command Line Arguments

- `input_file`: Input text file with one email per line
- `output_prefix`: Prefix for output files
- `--servers`: Comma-separated list of server addresses (host:port)
- `--batch-size`: Batch size for streaming (default: 100)
- `--max-workers`: Maximum worker threads (default: 10)
- `--timeout`: gRPC timeout in seconds (default: 30)
- `--retry-limit`: Number of retries per operation (default: 3)
- `--checkpoint`: How often to log progress (default: 1000)
- `--resume`: Resume from last run

### Output Files

The client creates three output files:

- `output_prefix_valid.txt`: Contains valid email addresses
- `output_prefix_invalid.txt`: Contains invalid or disposable email addresses
- `output_prefix_unknown.txt`: Contains emails with unknown status or errors

### Example

```
python client/email_validator_client.py email_addresses_1.txt results/output --servers 198.7.114.192:50051,198.7.114.193:50051,198.7.114.196:50051 --max-workers 12 --batch-size 200
```

## License

This project is licensed under the MIT License.
