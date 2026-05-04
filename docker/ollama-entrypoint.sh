#!/bin/sh

LLM_USE_GPU=${LLM_USE_GPU}

echo "📋 LLM_USE_GPU: $LLM_USE_GPU"

if [ "$LLM_USE_GPU" = "true" ]; then
    export NVIDIA_VISIBLE_DEVICES=all
    echo "⚡ GPU inference enabled for Ollama"
else
    echo "⚠️ CPU inference enabled for Ollama"
fi

echo "✅ Starting Ollama..."

# Start Ollama en filter GIN logs
exec /bin/ollama serve 2>&1 | grep -v "\[GIN\]"