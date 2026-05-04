#!/bin/sh

export PYTHONPATH=/app/src

echo "✅ Starting ifenpay-agent..."

# Start via app.py so preload/warm-up runs before serving traffic
cd /app
exec python -u app.py