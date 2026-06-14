# Build context is the repository root (see ../docker-compose.yml) because the
# backend depends on the sibling `mcp-server-example` package, which it spawns
# as a stdio subprocess (see app/config.py _default_servers()).
FROM python:3.12-slim

WORKDIR /app

COPY mcp-server-example/ ./mcp-server-example/
COPY backend/ ./backend/

RUN pip install --no-cache-dir ./mcp-server-example ./backend

WORKDIR /app/backend

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
