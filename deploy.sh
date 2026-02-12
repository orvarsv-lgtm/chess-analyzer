#!/bin/bash
set -euo pipefail

# ═══════════════════════════════════════════════════════════
# Chess Analyzer – VPS Deployment Script
# Run: ssh root@72.60.185.247 'bash -s' < deploy.sh
# Or:  ssh into VPS then: bash deploy.sh
# ═══════════════════════════════════════════════════════════

DOMAIN="chessanalyses.com"
REPO="https://github.com/orvarsv-lgtm/chess-analyzer.git"
APP_DIR="/opt/chess-analyzer"

echo "═══════════════════════════════════════════"
echo " Chess Analyzer – Production Deploy"
echo "═══════════════════════════════════════════"

# ─── 1. System Updates & Docker Install ──────────────────
echo "▸ Updating system..."
apt-get update -qq && apt-get upgrade -y -qq

if ! command -v docker &>/dev/null; then
    echo "▸ Installing Docker..."
    curl -fsSL https://get.docker.com | sh
    systemctl enable docker
    systemctl start docker
fi

if ! command -v docker &>/dev/null || ! docker compose version &>/dev/null; then
    echo "▸ Installing Docker Compose plugin..."
    apt-get install -y -qq docker-compose-plugin
fi

# ─── 2. Clone / Pull repo ────────────────────────────────
if [ -d "$APP_DIR" ]; then
    echo "▸ Updating existing repo..."
    cd "$APP_DIR"
    git pull origin main
else
    echo "▸ Cloning repository..."
    git clone "$REPO" "$APP_DIR"
    cd "$APP_DIR"
fi

# ─── 3. Environment file ─────────────────────────────────
if [ ! -f "$APP_DIR/.env" ]; then
    echo "▸ Creating .env from template..."
    cp "$APP_DIR/.env.production" "$APP_DIR/.env"

    # Generate secure passwords
    DB_PASS=$(openssl rand -base64 24 | tr -d '/+=')
    AUTH_SECRET=$(openssl rand -base64 32)

    sed -i "s|CHANGE_ME_USE_A_STRONG_PASSWORD|${DB_PASS}|g" "$APP_DIR/.env"
    sed -i "s|CHANGE_ME_GENERATE_WITH_openssl_rand_base64_32|${AUTH_SECRET}|g" "$APP_DIR/.env"

    echo ""
    echo "  ╔═══════════════════════════════════════════╗"
    echo "  ║  .env created with auto-generated secrets ║"
    echo "  ║  Edit /opt/chess-analyzer/.env to add:     ║"
    echo "  ║  - GOOGLE_CLIENT_ID (optional)             ║"
    echo "  ║  - OPENAI_API_KEY (optional)               ║"
    echo "  ╚═══════════════════════════════════════════╝"
    echo ""
fi

# ─── 4. Initial SSL Setup (HTTP-only first) ──────────────
# Start with a temporary nginx config that only serves HTTP
# so certbot can verify the domain
if [ ! -d "/etc/letsencrypt/live/$DOMAIN" ]; then
    echo "▸ Setting up initial SSL certificate..."

    # Create temp nginx config for HTTP-only
    mkdir -p "$APP_DIR/nginx"
    cat > "$APP_DIR/nginx/nginx.conf" << 'NGINX_TEMP'
server {
    listen 80;
    server_name chessanalyses.com www.chessanalyses.com;

    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }

    location / {
        proxy_pass http://frontend:3000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /api/ {
        proxy_pass http://backend:8000/api/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
NGINX_TEMP

    # Build and start services
    echo "▸ Building containers (this takes a few minutes)..."
    docker compose -f docker-compose.prod.yml build
    docker compose -f docker-compose.prod.yml up -d db backend frontend nginx

    echo "▸ Waiting for services to start..."
    sleep 15

    # Request certificate
    echo "▸ Requesting SSL certificate from Let's Encrypt..."
    docker compose -f docker-compose.prod.yml run --rm certbot \
        certbot certonly --webroot \
        -w /var/www/certbot \
        -d "$DOMAIN" -d "www.$DOMAIN" \
        --email "admin@$DOMAIN" \
        --agree-tos --no-eff-email \
        --force-renewal

    # Restore full nginx config with SSL
    echo "▸ Switching to SSL nginx config..."
    git checkout -- nginx/nginx.conf

    # Reload nginx with SSL
    docker compose -f docker-compose.prod.yml restart nginx
else
    echo "▸ SSL certificate already exists, building & starting..."
    docker compose -f docker-compose.prod.yml build
    docker compose -f docker-compose.prod.yml up -d
fi

# ─── 5. Health Check ─────────────────────────────────────
echo ""
echo "▸ Waiting for services to be healthy..."
sleep 10

echo ""
echo "▸ Container status:"
docker compose -f docker-compose.prod.yml ps

echo ""
echo "▸ Testing backend health..."
curl -sf http://localhost:8000/health && echo " ✅ Backend OK" || echo " ❌ Backend not responding"

echo ""
echo "═══════════════════════════════════════════"
echo " ✅ Deployment complete!"
echo ""
echo " Next steps:"
echo "   1. Point DNS: $DOMAIN → $(curl -s ifconfig.me)"
echo "   2. Wait for DNS propagation (~5 min)"
echo "   3. Visit https://$DOMAIN"
echo ""
echo " Useful commands:"
echo "   cd $APP_DIR"
echo "   docker compose -f docker-compose.prod.yml logs -f"
echo "   docker compose -f docker-compose.prod.yml restart"
echo "   docker compose -f docker-compose.prod.yml down"
echo "═══════════════════════════════════════════"
