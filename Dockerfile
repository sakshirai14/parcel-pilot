# --- Stage 1: Build the React Frontend ---
FROM node:22-alpine AS frontend-builder
WORKDIR /app/frontend

# Copy dependencies definitions
COPY frontend/package*.json ./
RUN npm ci

# Copy source code and build
COPY frontend/ ./
# VITE_API_URL is left empty so api.ts resolves dynamically to the current host
ENV VITE_API_URL=""
RUN npm run build

# --- Stage 2: Assembly and Backend Setup ---
FROM python:3.11-slim
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy backend dependencies and install
COPY backend/requirements.txt ./backend/
RUN pip install --no-cache-dir -r backend/requirements.txt

# Copy source folders
COPY backend/ ./backend/
COPY data/ ./data/

# Copy compiled frontend from builder
COPY --from=frontend-builder /app/frontend/dist ./frontend/dist

# Expose server port
EXPOSE 8000

# Set environment variables for runtime
ENV PORT=8000
ENV PYTHONPATH=/app

# Start the application
CMD ["sh", "-c", "uvicorn backend.app.main:app --host 0.0.0.0 --port $PORT"]
