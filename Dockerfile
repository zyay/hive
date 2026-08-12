FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install package
COPY pyproject.toml .
COPY hive/ hive/
RUN pip install --no-cache-dir -e .

# Copy remaining files
COPY . .

# Create data directories
RUN mkdir -p keystore relay_mailbox uploads skills

# HTTP API + P2P UDP
EXPOSE 8000
EXPOSE 4242/udp

CMD ["uvicorn", "hive.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
