#!/usr/bin/env bash
# Sample peak memory of the running crew containers. Writes a running max so the number
# survives the crew exiting.
OUT=/c/nscrev/reports/crew-memory-peak.txt
: > "$OUT"
peak=0
peakname=""
for i in $(seq 1 240); do
  while IFS='|' read -r name mem; do
    [ -z "$name" ] && continue
    case "$name" in *crew*|*claude-exec*) ;; *) continue ;; esac
    used=$(echo "$mem" | sed 's/ \/.*//')
    mb=$(python -c "
import re,sys
s='$used'.strip()
m=re.match(r'([0-9.]+)\s*([A-Za-z]+)', s)
if not m: print(0)
else:
    v=float(m.group(1)); u=m.group(2).lower()
    print(int(v*1024) if u.startswith('gi') or u.startswith('gb') else int(v))
" 2>/dev/null)
    [ -z "$mb" ] && mb=0
    if [ "$mb" -gt "$peak" ] 2>/dev/null; then peak=$mb; peakname="$name"; fi
  done < <(docker stats --no-stream --format '{{.Name}}|{{.MemUsage}}' 2>/dev/null)
  echo "sample $i: peak ${peak}MB ($peakname)" > "$OUT"
  if ! docker ps --format '{{.Names}}' 2>/dev/null | grep -q crew; then
    echo "PEAK ${peak}MB on $peakname; crew container gone at $(date +%H:%M:%S) after $i samples" >> "$OUT"
    exit 0
  fi
  sleep 15
done
echo "PEAK ${peak}MB on $peakname; sampler hit its 60-minute limit" >> "$OUT"
