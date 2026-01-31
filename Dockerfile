# syntax=docker/dockerfile:1
FROM python:3.11-slim

WORKDIR /app

# Runtime + build essentials:
# - rsync: required for file backup/restore
# - ca-certificates: TLS
# - docker-cli: needed if you want to control the host Docker engine (via /var/run/docker.sock mount)
# - make: to delegate install logic to Makefile
#
# Notes:
# - On Debian slim, the docker client package is typically "docker.io".
# - If you only want restore-without-docker, you can drop docker.io later.
RUN apt-get update && apt-get install -y --no-install-recommends \
    make \
    rsync \
    ca-certificates \
    docker.io \
    bash \
  && rm -rf /var/lib/apt/lists/*

# Fail fast if docker client is missing
RUN command -v docker

COPY . .

# All install decisions are handled by the Makefile.
RUN make install

# Sensible defaults (can be overridden at runtime)
ENV PYTHONUNBUFFERED=1

# Default: show CLI help
CMD ["baudolo", "--help"]
