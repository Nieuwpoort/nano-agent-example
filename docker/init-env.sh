#!/bin/sh
set -e

ENV_FILE="/host/.env"
ENV_EXAMPLE="/host/.env-example"

# Check if .env exists on host (mounted volume)
if [ ! -f "$ENV_FILE" ]; then
    echo "⚠️  No .env file found - creating from .env-example"
    
    # Copy template
    cp "$ENV_EXAMPLE" "$ENV_FILE"
    echo "✅ .env created"
else
    echo "✅ .env file already exists"
fi

echo "✅ Initialization complete!"
