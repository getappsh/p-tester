# Use Python 3.11 slim image as base
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Copy requirements first to leverage Docker cache
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the script
COPY getapp-test-script.py .

# Set environment variables with defaults
# ENV TEST_SCHEDULE="*/30 * * * *"
# ENV BASE_URL="http://localhost:3000"

# Expose Prometheus metrics port
EXPOSE 8000

# Run the script
CMD ["python", "api_test_script.py"]