# Multi-stage build for smaller final image

# Stage 1: Build stage
FROM python:3.10-slim as builder

WORKDIR /build

# Install build dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY kubernetes/phase6/requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir --user -r requirements.txt

# Stage 2: Runtime stage
FROM python:3.10-slim

WORKDIR /app

# Install runtime dependencies only
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy Python packages from builder
COPY --from=builder /root/.local /root/.local

# Make sure scripts in .local are usable
ENV PATH=/root/.local/bin:$PATH

# Create directory structure
RUN mkdir -p /app/src /app/models

# Copy application code
COPY kubernetes/phase6/prediction_service.py /app/
COPY src/*.py /app/src/

# Copy model checkpoint
COPY models/tft_psi_model.ckpt /app/models/

# Create non-root user
RUN useradd -m -u 1000 predictor && \
    chown -R predictor:predictor /app

USER predictor

# Expose ports
EXPOSE 8080 9090

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

# Run the service
CMD ["python", "/app/prediction_service.py"]
