#!/bin/bash
set -x  # Enable script debugging
echo "Copying default configuration to Nginx sites-available..."
cp -rf default /etc/nginx/sites-available/default

echo "Reloading Nginx..."
nginx -s reload

echo "ehridentityst"
pm2 start "streamlit run /ehridentityst/ehridentityst.py --server.port 8501 --server.address 0.0.0.0" \
  --name my-ehridentityst-app \
  --output ehridentityst-out.log \
  --error ehridentityst-error.log
