#!/bin/bash
set -x  # Enable script debugging
echo "Copying default configuration to Nginx sites-available..."
cp -rf default /etc/nginx/sites-available/default

echo "Reloading Nginx..."
nginx -s reload

echo "ehridentityag"
echo "Starting Gunicorn server..."
gunicorn -w 1\
 --daemon ehridentityag:app\
 --bind 0.0.0.0:8000\
 --error-logfile ./error.log\
 --access-logfile ./access.log\
 --capture-output --log-level debug
