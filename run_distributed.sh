#!/bin/bash

# Run distributed email validation across multiple servers
# Usage: ./run_distributed.sh input_file output_dir server1:port1,server2:port2,server3:port3

if [ "$#" -lt 3 ]; then
    echo "Usage: $0 <input_file> <output_dir> <server1:port1,server2:port2,...> [workers_per_server] [batch_size]"
    exit 1
fi

INPUT_FILE=$1
OUTPUT_DIR=$2
SERVERS=$3
WORKERS_PER_SERVER=${4:-5}
BATCH_SIZE=${5:-100}

# Create output directory if it doesn't exist
mkdir -p "$OUTPUT_DIR"

# Split the input file into chunks (one per server)
echo "Splitting input file into chunks..."
TOTAL_LINES=$(wc -l < "$INPUT_FILE")
SERVER_COUNT=$(echo "$SERVERS" | tr ',' '\n' | wc -l)
LINES_PER_SERVER=$((TOTAL_LINES / SERVER_COUNT + 1))

split -l "$LINES_PER_SERVER" "$INPUT_FILE" "$OUTPUT_DIR/chunk_"

# Start a client for each server
echo "Starting clients for each server..."
SERVER_ARRAY=($(echo "$SERVERS" | tr ',' ' '))
CHUNK_FILES=($(ls "$OUTPUT_DIR/chunk_"*))

for i in "${!SERVER_ARRAY[@]}"; do
    if [ $i -lt ${#CHUNK_FILES[@]} ]; then
        SERVER="${SERVER_ARRAY[$i]}"
        CHUNK="${CHUNK_FILES[$i]}"
        OUTPUT_PREFIX="$OUTPUT_DIR/result_$(basename "$CHUNK")"
        
        echo "Starting client for server $SERVER with chunk $CHUNK"
        # Run in background
        python client/email_validator_client.py "$CHUNK" "$OUTPUT_PREFIX" \
            --servers "$SERVER" \
            --max-workers "$WORKERS_PER_SERVER" \
            --batch-size "$BATCH_SIZE" \
            --retry-limit 3 \
            --timeout 30 > "$OUTPUT_DIR/log_$(basename "$CHUNK").log" 2>&1 &
        
        # Store the process ID
        echo "$!" > "$OUTPUT_DIR/pid_$(basename "$CHUNK").pid"
        
        # Sleep to avoid all clients starting at exactly the same time
        sleep 2
    fi
done

echo "All clients started. Monitor progress with:"
echo "tail -f $OUTPUT_DIR/log_*"
echo ""
echo "To stop all clients:"
echo "./stop_distributed.sh $OUTPUT_DIR" 