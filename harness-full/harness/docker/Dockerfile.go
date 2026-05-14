FROM golang:1.22-bookworm

# Install optional tools
RUN go install honnef.co/go/tools/cmd/staticcheck@latest && \
    go install github.com/securego/gosec/v2/cmd/gosec@latest

# Create non-root user
RUN useradd -m -u 1000 harness
USER harness
WORKDIR /work
