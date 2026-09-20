#!/usr/bin/env bash
# Wait for crew containers to exit, then settle the cancelled runs so they can be re-dispatched.
cd /c/NSC/NSC/NoSafeCircle
for i in $(seq 1 60); do
  if ! docker ps --format '{{.Names}}' 2>/dev/null | grep -q crew; then
    echo "containers gone at $(date +%H:%M:%S)"
    for pair in "NSC-097 task-orch-nsc097-20260917-1" "NSC-046 task-orch-nsc046-20260917-1"; do
      set -- $pair
      echo "--- settle $1 ---"
      timeout 180 python -m Pipeline.AssistantControl --source C:/NSC/NSC/NoSafeCircle \
        --checkout-root C:/NSC/NoSafeCircle-AssistantCheckouts settle-worker "$1" --run-id "$2" 2>&1 | head -5
    done
    exit 0
  fi
  sleep 10
done
echo "crew containers still up after 10 minutes - settle not attempted"
