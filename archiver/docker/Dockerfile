FROM python:3.11-slim

WORKDIR /app

# System deps for psycopg2 and pg tools
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Merge requirements from both scanner and webui
COPY scanner/requirements.txt /tmp/scanner-requirements.txt
COPY webui/requirements.txt /tmp/webui-requirements.txt
RUN pip install --no-cache-dir \
    -r /tmp/scanner-requirements.txt \
    -r /tmp/webui-requirements.txt \
    && rm /tmp/*-requirements.txt

# Copy everything
COPY scanner/ ./scanner/
COPY webui/ ./webui/
COPY migrations/ ./migrations/

RUN mkdir -p /app/logs

EXPOSE 8480

CMD ["uvicorn", "webui.main:app", "--host", "0.0.0.0", "--port", "8480"]
