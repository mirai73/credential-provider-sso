FROM python:3.12-slim

RUN pip install --no-cache-dir boto3==1.35.0

RUN useradd -r -m appuser
USER appuser

COPY server.py /app/server.py
WORKDIR /app

CMD ["python", "-u", "server.py"]
