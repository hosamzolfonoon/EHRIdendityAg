#!/bin/bash
set -x  # Enable script debugging
echo "Copying default configuration to Nginx sites-available..."
cp -rf default /etc/nginx/sites-available/default

echo "Reloading Nginx..."
nginx -s reload

echo "identityagent"
pm2 start "streamlit run /identityagent/identityagent.py --server.port 8501 --server.address 0.0.0.0" \
  --name my-identityagent-app \
  --output identityagent-out.log \
  --error identityagent-error.log
