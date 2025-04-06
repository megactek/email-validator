# Email Validation System: User Guide

This guide provides step-by-step instructions on how to set up and run the distributed email validation system.

## Prerequisites

- Go 1.18+ (for the server)
- Python 3.8+ (for the client)
- Protocol Buffers compiler

## Setup

### Server Setup

1. **Prepare the source IP addresses**:
   Edit `server/source_ips.txt` to include your outbound IP addresses:

   ```
   192.168.1.1
   192.168.1.2
   # Add your actual IPs here
   ```

2. **Build the server**:

   ```bash
   cd server
   chmod +x generate_proto.sh
   ./generate_proto.sh
   make build
   ```

3. **Run the server** on each of your validation machines:
   ```bash
   ./email_validator --port=50051 --rate-limit=20
   ```

### Client Setup

1. **Install Python dependencies**:

   ```bash
   cd client
   pip install -r requirements.txt
   ```

2. **Generate the Protocol Buffer code**:
   ```bash
   chmod +x generate_proto.sh
   ./generate_proto.sh
   ```

## Validation Workflow

### Single Server Validation

For testing or small email lists:

```bash
cd client
python email_validator_client.py input.txt output_prefix --servers=server1:50051
```

### Distributed Validation

For large email lists (millions of emails):

1. **Split and distribute the workload**:

   ```bash
   ./run_distributed.sh large_email_list.txt output_dir server1:50051,server2:50051,server3:50051
   ```

2. **Monitor progress**:

   ```bash
   tail -f output_dir/log_*
   ```

3. **Stop all validation processes** (if needed):

   ```bash
   ./stop_distributed.sh output_dir
   ```

4. **Merge results** when validation is complete:
   ```bash
   ./merge_results.sh output_dir merged_results
   ```

## Output Files

After running the validation, you'll get these output files:

- `{prefix}_valid.txt`: Valid email addresses
- `{prefix}_invalid.txt`: Invalid email addresses
- `{prefix}_disposable.txt`: Disposable email addresses
- `{prefix}_unknown.txt`: Emails where validation status couldn't be determined

## Performance Optimization

- Adjust the `--max-workers` parameter in the client to control concurrency
- Modify the `--batch-size` parameter to change how many emails are processed in each batch
- Use more server instances to increase throughput
- Edit the source IP rotation in the server for better block prevention

## Troubleshooting

### Connection Issues

- Ensure the server is running and the port is accessible
- Check firewall settings to allow the gRPC port

### Rate Limiting Issues

- Increase the number of source IPs in `source_ips.txt`
- Decrease the client concurrency with `--max-workers`
- Adjust the server's `--rate-limit` parameter

### Memory Issues

- Reduce the batch size with `--batch-size`
- Monitor server memory usage and increase server resources if necessary
