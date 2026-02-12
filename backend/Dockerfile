FROM python:3.12-slim

# Install Stockfish
RUN apt-get update && \
    apt-get install -y --no-install-recommends stockfish && \
    rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements first for caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the app
COPY . .

# Expose port (Railway sets PORT env var)
EXPOSE 8000

# Start the server — Railway provides $PORT
CMD uvicorn run:app --host 0.0.0.0 --port ${PORT:-8000}
