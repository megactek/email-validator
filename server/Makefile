# Go parameters
GOCMD=go
GOBUILD=$(GOCMD) build
GOTEST=$(GOCMD) test
GOGET=$(GOCMD) get
BINARY_NAME=email_validator
PROTO_DIR=proto

.PHONY: all proto build test clean run deps

PROTOC_GEN_GO := $(shell which protoc-gen-go)
PROTOC_GEN_GO_GRPC := $(shell which protoc-gen-go-grpc)

all: proto build

proto:
	@echo "Generating protocol buffer code..."
	@chmod +x generate_proto.sh
	@./generate_proto.sh

build: proto
	@echo "Building server..."
	$(GOBUILD) -o $(BINARY_NAME) -v

test:
	@echo "Running tests..."
	$(GOTEST) -v ./...

clean:
	@echo "Cleaning up..."
	@rm -f $(BINARY_NAME)
	@rm -f $(PROTO_DIR)/*.pb.go

run:
	@echo "Running server..."
	@./$(BINARY_NAME)

deps:
	@echo "Fetching dependencies..."
	$(GOGET) -v google.golang.org/protobuf/cmd/protoc-gen-go
	$(GOGET) -v google.golang.org/grpc/cmd/protoc-gen-go-grpc
	$(GOGET) -v google.golang.org/grpc

	@if [ -z "$(PROTOC_GEN_GO)" ]; then \
		echo "Installing protoc-gen-go..."; \
		go install google.golang.org/protobuf/cmd/protoc-gen-go@latest; \
	fi
	@if [ -z "$(PROTOC_GEN_GO_GRPC)" ]; then \
		echo "Installing protoc-gen-go-grpc..."; \
		go install google.golang.org/grpc/cmd/protoc-gen-go-grpc@latest; \
	fi
	mkdir -p proto
	protoc --go_out=. --go_opt=paths=source_relative \
		--go-grpc_out=. --go-grpc_opt=paths=source_relative \
		proto/email_validator.proto 