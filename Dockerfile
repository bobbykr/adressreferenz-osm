# Werkzeuge für den Auszug (bau-auszug.sh auf dem Bau-Server, seit 12.11.2026 statt GitHub Actions).
# Entspricht dem Schritt „Werkzeuge“ des alten Workflows: osmium-tool und Python mit requirements.txt.
FROM ubuntu:24.04
RUN apt-get update -q \
 && DEBIAN_FRONTEND=noninteractive apt-get install -y -q --no-install-recommends \
      osmium-tool python3 python3-venv curl ca-certificates time \
 && rm -rf /var/lib/apt/lists/*
COPY requirements.txt /opt/auszug/requirements.txt
RUN python3 -m venv /opt/venv && /opt/venv/bin/pip install -q --no-cache-dir -r /opt/auszug/requirements.txt
ENV PATH=/opt/venv/bin:$PATH
