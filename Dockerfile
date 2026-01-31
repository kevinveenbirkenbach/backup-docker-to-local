# syntax=docker/dockerfile:1
FROM python:3.11-slim

WORKDIR /app

# Base deps for build/runtime + docker repo key
RUN apt-get update && apt-get install -y --no-install-recommends \
    make \
    rsync \
    ca-certificates \
    bash \
    curl \
    gnupg \
  && rm -rf /var/lib/apt/lists/*

# Install Docker CLI (docker-ce-cli) from Docker's official apt repo
RUN bash -lc "set -euo pipefail \
  && install -m 0755 -d /etc/apt/keyrings \
  && curl -fsSL https://download.docker.com/linux/debian/gpg \
     | gpg --dearmor -o /etc/apt/keyrings/docker.gpg \
  && chmod a+r /etc/apt/keyrings/docker.gpg \
  && . /etc/os-release \
  && echo \"deb [arch=\$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/debian \${VERSION_CODENAME} stable\" \
     > /etc/apt/sources.list.d/docker.list \
  && apt-get update \
  && apt-get install -y --no-install-recommends docker-ce-cli \
  && rm -rf /var/lib/apt/lists/*"

# Fail fast if docker client is missing
RUN docker version || true
RUN command -v docker

COPY . .
RUN make install

ENV PYTHONUNBUFFERED=1
CMD ["baudolo", "--help"]
