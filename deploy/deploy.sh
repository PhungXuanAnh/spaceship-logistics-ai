#!/usr/bin/env bash
# Builds backend+frontend images locally, transfers them to the EC2 box via ssh,
# loads them into Docker, writes .env, and runs `docker compose up -d`.
#
# Required env vars (overridable via .env in this dir):
#   PUBLIC_IP        - EC2 EIP (from terraform output public_ip)
#   DOMAIN           - public domain (e.g. spaceship.xuananh1.site)
#   JWT_SECRET       - 32+ char random string
#   DEMO_EMAIL       - default demo@spaceship.test
#   DEMO_PASSWORD    - default demo123
#   LLM_PROVIDER     - keyword (default), claude, gemini
#   LLM_MODEL/LLM_API_KEY/FALLBACK_*  - if non-keyword
#
# Usage:
#   cd deploy
#   PUBLIC_IP=1.2.3.4 DOMAIN=spaceship.xuananh1.site \
#     JWT_SECRET="$(openssl rand -hex 32)" ./deploy.sh

set -euo pipefail
cd "$(dirname "$0")"

if [[ -f .env ]]; then set -a; . ./.env; set +a; fi

: "${PUBLIC_IP:?PUBLIC_IP required (terraform output public_ip)}"
: "${DOMAIN:?DOMAIN required}"
: "${JWT_SECRET:?JWT_SECRET required (use: openssl rand -hex 32)}"
DEMO_EMAIL="${DEMO_EMAIL:-demo@spaceship.test}"
DEMO_PASSWORD="${DEMO_PASSWORD:-demo123}"
LLM_PROVIDER="${LLM_PROVIDER:-keyword}"
LLM_MODEL="${LLM_MODEL:-}"
LLM_API_KEY="${LLM_API_KEY:-}"
FALLBACK_PROVIDER="${FALLBACK_PROVIDER:-keyword}"
FALLBACK_MODEL="${FALLBACK_MODEL:-}"
FALLBACK_API_KEY="${FALLBACK_API_KEY:-}"

KEY="../infra/spaceship-deploy.pem"
CTRL="/tmp/ssh-spaceship-ctrl-$$"
SSH_OPTS="-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o IdentitiesOnly=yes -o LogLevel=ERROR -o ControlMaster=auto -o ControlPath=$CTRL -o ControlPersist=10m -o ServerAliveInterval=15 -o ServerAliveCountMax=4 -o ConnectTimeout=30"
SSH="ssh $SSH_OPTS -i $KEY ubuntu@$PUBLIC_IP"
SCP="scp $SSH_OPTS -i $KEY"
trap 'ssh $SSH_OPTS -i $KEY -O exit ubuntu@$PUBLIC_IP 2>/dev/null || true; rm -f $CTRL' EXIT

echo "[1/6] Building backend image..."
docker build --platform=linux/amd64 -t spaceship-backend:latest ../backend

echo "[2/6] Building frontend image..."
# Bake the public origin (IP for now, swap to https://DOMAIN after DNS+cert ready).
PUBLIC_API_URL="${PUBLIC_API_URL:-http://${PUBLIC_IP}}"
echo "  using NEXT_PUBLIC_API_URL=$PUBLIC_API_URL"
docker build --platform=linux/amd64 --build-arg NEXT_PUBLIC_API_URL="$PUBLIC_API_URL" -t spaceship-frontend:latest ../frontend

echo "[3/6] Saving images to tarballs..."
docker save spaceship-backend:latest spaceship-frontend:latest | gzip > /tmp/spaceship-images.tgz

echo "[4/6] Waiting for EC2 cloud-init to finish..."
for i in {1..30}; do
  if $SSH "test -f /var/log/spaceship-bootstrap-done"; then echo "  ...ready"; break; fi
  echo "  waiting (attempt $i/30)..."; sleep 10
done

echo "[5/6] Copying images + compose files to EC2..."
$SSH "mkdir -p ~/spaceship && sudo install -d -o ubuntu /var/spaceship/data /var/spaceship/caddy_data /var/spaceship/caddy_config"
$SCP /tmp/spaceship-images.tgz ubuntu@"$PUBLIC_IP":~/spaceship/
$SCP compose.yml Caddyfile ubuntu@"$PUBLIC_IP":~/spaceship/

# write .env on the box (no secrets in repo)
$SSH "cat > ~/spaceship/.env" <<EOF
DOMAIN=${DOMAIN}
JWT_SECRET=${JWT_SECRET}
DEMO_EMAIL=${DEMO_EMAIL}
DEMO_PASSWORD=${DEMO_PASSWORD}
LLM_PROVIDER=${LLM_PROVIDER}
LLM_MODEL=${LLM_MODEL}
LLM_API_KEY=${LLM_API_KEY}
FALLBACK_PROVIDER=${FALLBACK_PROVIDER}
FALLBACK_MODEL=${FALLBACK_MODEL}
FALLBACK_API_KEY=${FALLBACK_API_KEY}
EOF

echo "[6/6] Loading images and (re)starting compose..."
$SSH "cd ~/spaceship && gunzip -c spaceship-images.tgz | docker load && docker compose --env-file .env -f compose.yml up -d --remove-orphans && rm -f spaceship-images.tgz"

echo "Done. Public IP: $PUBLIC_IP"
echo "Once DNS resolves: https://$DOMAIN"
