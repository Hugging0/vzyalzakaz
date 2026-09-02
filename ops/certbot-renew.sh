#!/usr/bin/env sh
set -eu

docker run --rm \
  -v /etc/letsencrypt:/etc/letsencrypt \
  -v huntagent_certbot_www:/var/www/certbot \
  certbot/certbot:latest \
  renew --cert-name vzyalzakaz.ru --quiet

cd /opt/hunt-agent
docker compose \
  --project-name huntagent \
  -f compose.yaml \
  -f compose.production.yaml \
  exec -T nginx nginx -s reload
