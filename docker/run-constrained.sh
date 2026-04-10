#!/usr/bin/env bash
# Same limits as docker-compose, using `docker run` so CPU/RAM caps always apply.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

IMAGE="${IMAGE:-predictivetheory:local}"
docker build -t "$IMAGE" -f Dockerfile .

exec docker run --rm \
  --name predictivetheory-constrained \
  -p 8500:8500 \
  --memory=1g \
  --memory-swap=1g \
  --cpus=2 \
  --tmpfs /app/data:size=1G,mode=1777 \
  "$IMAGE"
