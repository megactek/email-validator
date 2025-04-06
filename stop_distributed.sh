#!/bin/bash

# Stop all distributed email validation clients
# Usage: ./stop_distributed.sh output_dir

if [ "$#" -lt 1 ]; then
    echo "Usage: $0 <output_dir>"
    exit 1
fi

OUTPUT_DIR=$1

# Check if output directory exists
if [ ! -d "$OUTPUT_DIR" ]; then
    echo "Error: Output directory $OUTPUT_DIR does not exist."
    exit 1
fi

# Find all PID files
PID_FILES=$(ls "$OUTPUT_DIR"/pid_*.pid 2>/dev/null)

if [ -z "$PID_FILES" ]; then
    echo "No running clients found in $OUTPUT_DIR."
    exit 0
fi

# Stop each client
for PID_FILE in $PID_FILES; do
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        CLIENT_NAME=$(basename "$PID_FILE" .pid)
        
        if ps -p "$PID" > /dev/null 2>&1; then
            echo "Stopping client $CLIENT_NAME (PID: $PID)..."
            kill -SIGINT "$PID"
            
            # Wait for process to finish gracefully
            for i in {1..30}; do
                if ! ps -p "$PID" > /dev/null 2>&1; then
                    break
                fi
                echo "Waiting for client to shutdown... ($i/30)"
                sleep 1
            done
            
            # Force kill if still running
            if ps -p "$PID" > /dev/null 2>&1; then
                echo "Client didn't shut down gracefully. Force killing..."
                kill -9 "$PID"
            else
                echo "Client $CLIENT_NAME shut down gracefully."
            fi
        else
            echo "Client $CLIENT_NAME (PID: $PID) is not running."
        fi
        
        # Remove PID file
        rm "$PID_FILE"
    fi
done

echo "All clients stopped." 