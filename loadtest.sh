#!/usr/bin/env bash
D="$1"; N="${2:-900}"
args=()
for f in $(ls "$D"/*.json | head -"$N"); do args+=(-F "files=@$f"); done
echo "uploading ${#args[@]} form fields"
curl -s -o /dev/null -w "batch: HTTP %{http_code} in %{time_total}s\n" \
  -X POST http://127.0.0.1:8000/ingest "${args[@]}" &
for i in $(seq 1 10); do
  curl -s -o /dev/null -w "health: %{time_total}s\n" http://127.0.0.1:8000/health
  sleep 0.5
done
wait
