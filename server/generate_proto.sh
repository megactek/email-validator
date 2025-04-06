#!/bin/bash

# Check if protoc is installed
if ! command -v protoc &> /dev/null; then
    echo "Error: protoc is not installed or not in PATH"
    echo "Please install Protocol Buffers compiler from https://github.com/protocolbuffers/protobuf/releases"
    exit 1
fi

# Check if Go plugins are installed
if ! command -v protoc-gen-go &> /dev/null || ! command -v protoc-gen-go-grpc &> /dev/null; then
    echo "Installing Go plugins for Protocol Buffers..."
    go install google.golang.org/protobuf/cmd/protoc-gen-go@latest
    go install google.golang.org/grpc/cmd/protoc-gen-go-grpc@latest
fi

# Create directories if they don't exist
mkdir -p ./proto

# Generate protocol buffer code
echo "Generating Go protocol buffer code..."
protoc --go_out=. --go_opt=paths=source_relative \
    --go-grpc_out=. --go-grpc_opt=paths=source_relative \
    proto/email_validator.proto

echo "Protocol buffer code generation complete!" 