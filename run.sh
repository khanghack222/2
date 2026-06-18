#!/bin/bash
# run.sh — Auto-restart wrapper for bot.py
# Usage: ./run.sh [max_restarts]

MAX_RESTARTS=${1:-0}
RESTART_DELAY=3
COUNTER=0

echo "================================================"
echo "  Bot Runner with Auto-Restart"
echo "  Max restarts: $MAX_RESTARTS (0 = unlimited)"
echo "================================================"

while true; do
    echo "[$(date)] Starting bot..."
    python bot.py
    EXIT_CODE=$?
    COUNTER=$((COUNTER + 1))
    
    echo "[$(date)] Bot exited with code $EXIT_CODE"
    
    if [ $MAX_RESTARTS -gt 0 ] && [ $COUNTER -ge $MAX_RESTARTS ]; then
        echo "[$(date)] Reached max restarts ($MAX_RESTARTS). Exiting."
        exit $EXIT_CODE
    fi
    
    echo "[$(date)] Restarting in ${RESTART_DELAY}s... (attempt $COUNTER)"
    sleep $RESTART_DELAY
done
