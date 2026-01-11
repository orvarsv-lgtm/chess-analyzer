#!/bin/bash
# Chess Analyzer - VPS Deployment Script
# Targeted for Ubuntu 24.04

set -e

echo "🚀 Starting deployment on Hostinger VPS..."

# 1. Update System
apt update && apt upgrade -y

# 2. Install Dependencies
apt install -y python3-venv python3-dev build-essential git curl stockfish nginx ufw

# 3. Setup Project Directory (assuming run from root of repo)
PROJECT_DIR=$(pwd)
VENV_DIR="$PROJECT_DIR/.venv"

# 4. Create Virtual Environment if it doesn't exist
if [ ! -d "$VENV_DIR" ]; then
    python3 -m venv "$VENV_DIR"
fi

# 5. Install Python Requirements
source "$VENV_DIR/bin/activate"
pip install --upgrade pip
pip install -r requirements.txt

# 5.1 Prompt for Supabase Credentials (Optional)
echo "-------------------------------------------------------"
echo "🔧 Supabase Configuration (Optional)"
echo "If you use Supabase for global puzzles/ratings, enter details now."
echo "Press Enter to skip if using local storage only."
read -p "PUZZLE_BANK_BACKEND (local/supabase) [local]: " SB_BACKEND
SB_BACKEND=${SB_BACKEND:-local}

if [ "$SB_BACKEND" = "supabase" ]; then
    read -p "SUPABASE_URL: " SB_URL
    read -p "SUPABASE_SERVICE_ROLE_KEY: " SB_KEY
fi
echo "-------------------------------------------------------"

# 6. Configure Firewall
ufw allow 80
ufw allow 443
ufw allow 22
ufw --force enable

# 7. Create Systemd Service
cat <<EOF > /etc/systemd/system/chess-analyzer.service
[Unit]
Description=Streamlit Chess Analyzer
After=network.target

[Service]
User=root
WorkingDirectory=$PROJECT_DIR
Environment=STOCKFISH_PATH=/usr/games/stockfish
Environment=PUZZLE_BANK_BACKEND=$SB_BACKEND
Environment=SUPABASE_URL=$SB_URL
Environment=SUPABASE_SERVICE_ROLE_KEY=$SB_KEY
Environment=PATH=$VENV_DIR/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
ExecStart=$VENV_DIR/bin/streamlit run streamlit_app.py --server.port 8501 --server.address 0.0.0.0

[Install]
WantedBy=multi-user.target
EOF

# 8. Setup Nginx Reverse Proxy
cat <<EOF > /etc/nginx/sites-available/chess-analyzer
server {
    listen 80;
    server_name 148.230.107.44;

    location / {
        proxy_pass http://127.0.0.1:8501;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host \$host;
        proxy_cache_bypass \$http_upgrade;
    }
}
EOF

ln -sf /etc/nginx/sites-available/chess-analyzer /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default

# 9. Start Services
systemctl daemon-reload
systemctl enable chess-analyzer
systemctl restart chess-analyzer
systemctl restart nginx

echo "✅ Deployment complete!"
echo "🌍 App is now live at http://148.230.107.44"
echo "🛠️ To check logs run: journalctl -u chess-analyzer -f"
