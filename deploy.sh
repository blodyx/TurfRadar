#!/usr/bin/env bash

set -euo pipefail

cd "$(dirname "$0")"

echo "== TurfRadar deploy =="

echo "1/4 Validate Compose"
docker compose config --quiet

echo "2/4 Build and start services"
docker compose up -d --build

echo "3/4 Deploy frontend"
install \
  -m 0644 \
  frontend/index.html \
  /var/www/turfradar/index.html

echo "4/4 Service status"
docker compose ps

echo
echo "TurfRadar deployed."
echo "https://farstad.se/turfradar/"
