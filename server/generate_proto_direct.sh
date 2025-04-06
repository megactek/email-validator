#!/bin/bash

# Create directories if they don't exist
mkdir -p ./proto

# Define proto directory
PROTO_DIR="./proto"
PROTO_FILE="$PROTO_DIR/email_validator.proto"

echo "Generating Go code from Protocol Buffers directly..."

# Generate Go code using go run directly
go run google.golang.org/protobuf/cmd/protoc-gen-go@latest $PROTO_FILE
go run google.golang.org/grpc/cmd/protoc-gen-go-grpc@latest $PROTO_FILE

echo "Protocol buffer code generation complete!" 