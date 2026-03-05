# Multi-stage build for poor-cli
FROM python:3.11-slim as builder

# Set working directory
WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir --user -r requirements.txt

# Final stage
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install runtime dependencies
RUN apt-get update && apt-get install -y \
    git \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd -r pooruser && useradd -r -g pooruser -m pooruser

# Copy Python dependencies from builder
COPY --from=builder /root/.local /home/pooruser/.local

# Copy application code
COPY --chown=pooruser:pooruser . .

# Install poor-cli
RUN pip install --no-cache-dir -e .

# Set environment variables
ENV PATH=/home/pooruser/.local/bin:$PATH
ENV PYTHONUNBUFFERED=1

# Create volume for persistent data
RUN mkdir -p /home/pooruser/.poor-cli && chown pooruser:pooruser /home/pooruser/.poor-cli
VOLUME ["/home/pooruser/.poor-cli"]

# Switch to non-root user
USER pooruser

# Entry point
ENTRYPOINT ["poor-cli"]

# Default command
CMD []
