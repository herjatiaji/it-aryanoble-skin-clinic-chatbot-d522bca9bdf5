# Stage 1: Build React Frontend
FROM node:20-alpine as frontend-builder
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install
COPY frontend/ .
RUN npm run build

# Stage 2: Build FastAPI Backend
FROM python:3.11-slim
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
# Copy the built frontend from Stage 1
COPY --from=frontend-builder /app/frontend/dist /app/frontend/dist

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]
