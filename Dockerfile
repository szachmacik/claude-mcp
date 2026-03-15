FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY server.py .

# FASTMCP_HOST / FASTMCP_PORT control where SSE server listens
ENV FASTMCP_HOST=0.0.0.0
ENV FASTMCP_PORT=8080

EXPOSE 8080

ENV PYTHONUNBUFFERED=1

CMD ["python", "server.py"]
