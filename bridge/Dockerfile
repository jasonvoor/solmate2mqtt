FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY bridge.py .

# Run unbuffered so logs appear immediately under `docker compose logs -f`.
CMD ["python", "-u", "bridge.py"]
