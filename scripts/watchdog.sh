#!/usr/bin/env bash
# Watchdog: auto-restart llama-server and assistant if they crash
# Also drops caches periodically to prevent OOM

LLAMA_BIN="/opt/llama.cpp/build/bin/server"
LLAMA_MODEL="/opt/models/gemma-2b-it-q4_k_m.gguf"
LLAMA_ARGS="--alias gemma-2b-it --host 127.0.0.1 --port 8080 -c 256 -t 4 -ngl 99 -n 120"
ASSISTANT_DIR="/home/jetson/edge_voice_assistant"
ENV_FILE="$ASSISTANT_DIR/.env"
CHECK_INTERVAL=15

start_llama() {
    echo "[watchdog] Starting llama-server..."
    sudo sh -c "echo 3 > /proc/sys/vm/drop_caches" 2>/dev/null
    sleep 1
    nohup "$LLAMA_BIN" -m "$LLAMA_MODEL" $LLAMA_ARGS > /tmp/llama-server.log 2>&1 &
    sleep 10
    if curl -s http://127.0.0.1:8080/v1/models > /dev/null 2>&1; then
        echo "[watchdog] llama-server started OK"
    else
        echo "[watchdog] llama-server failed to start"
    fi
}

start_assistant() {
    echo "[watchdog] Starting assistant..."
    cd "$ASSISTANT_DIR"
    set -a; source "$ENV_FILE"; set +a
    nohup python3 app.py --mode local > /tmp/edge-assistant.log 2>&1 &
    sleep 3
}

check_llama() {
    curl -s --max-time 5 http://127.0.0.1:8080/v1/models > /dev/null 2>&1
}

check_assistant() {
    curl -s --max-time 5 http://127.0.0.1:8000/api/status > /dev/null 2>&1
}

# Initial start
start_llama
start_assistant

echo "[watchdog] Monitoring started (every ${CHECK_INTERVAL}s)"
while true; do
    sleep "$CHECK_INTERVAL"

    if ! check_llama; then
        echo "[watchdog] $(date): llama-server down, restarting..."
        killall -9 server 2>/dev/null
        sleep 2
        start_llama
    fi

    if ! check_assistant; then
        echo "[watchdog] $(date): assistant down, restarting..."
        killall -9 python3 2>/dev/null
        sleep 2
        start_assistant
    fi

    # Drop caches if available memory < 300MB
    AVAIL=$(awk '/MemAvailable/{print int($2/1024)}' /proc/meminfo)
    if [ "$AVAIL" -lt 300 ] 2>/dev/null; then
        echo "[watchdog] $(date): Low memory (${AVAIL}MB), dropping caches"
        sudo sh -c "echo 3 > /proc/sys/vm/drop_caches" 2>/dev/null
    fi
done
