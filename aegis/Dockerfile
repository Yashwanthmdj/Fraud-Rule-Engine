# ---- build the React review console ----
FROM node:18-alpine AS console
WORKDIR /console
COPY frontend/package*.json ./
RUN npm ci --silent
COPY frontend/ ./
RUN npm run build

# ---- API + rule engine ----
FROM python:3.11-slim
WORKDIR /app/backend
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ ./
COPY examples/ /app/examples/
COPY --from=console /console/dist /app/frontend/dist
ENV AEGIS_DB_URL=sqlite:////data/aegis.db
VOLUME /data
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
