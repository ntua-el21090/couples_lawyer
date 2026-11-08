# One image for the whole app: FastAPI serves the API, the photos and the built frontend.

# Stage 1: build the React frontend with Node. Node is only needed here, not at runtime.
FROM node:22-slim AS frontend
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Stage 2: the Python app.
FROM python:3.11-slim
WORKDIR /app
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
# Only the app itself. The tests, the virtual environment and the original photos in
# pictures/ are not copied in.
COPY backend/app ./app
COPY --from=frontend /build/dist ./frontend_dist

# Run as an ordinary user, not root.
RUN useradd --system --no-create-home appuser
USER appuser

# Production mode refuses to start without ACCESS_PASSCODE.
ENV LAWYER_ENV=production FRONTEND_DIST=/app/frontend_dist
# Render sets PORT. The default matches Render's.
CMD ["sh", "-c", "exec uvicorn app.main:create_app --factory --host 0.0.0.0 --port ${PORT:-10000}"]
