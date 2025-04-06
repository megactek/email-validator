#!/bin/bash

# Generate Python code from protocol buffer definition
python -m grpc_tools.protoc -I. --python_out=. --grpc_python_out=. email_validator.proto

echo "Protocol buffer code generated successfully." 