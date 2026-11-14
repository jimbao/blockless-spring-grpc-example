#!/usr/bin/env bash
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
results="$root/results"
mkdir -p "$results"
app_pid=''
cleanup() {
  if [[ -n "$app_pid" ]]; then
    kill "$app_pid" 2>/dev/null || true
    wait "$app_pid" 2>/dev/null || true
    app_pid=''
  fi
  docker rm -f blockless-perf-db >/dev/null 2>&1 || true
}
trap cleanup EXIT
for variant in base candidate; do
  (cd "$root/$variant" && mvn -B -Dfmt.skip=true -DskipTests package) >"$results/$variant-build.log" 2>&1
done
for repetition in 1 2 3 4 5; do
  order='base candidate'
  if (( repetition % 2 == 0 )); then order='candidate base'; fi
  for variant in $order; do
    cleanup
    destination="$results/$variant/$repetition"
    mkdir -p "$destination"
    docker run -d --name blockless-perf-db -p 5433:5432 \
      -e POSTGRES_DB=benchmark -e POSTGRES_USER=postgres -e POSTGRES_PASSWORD=postgres \
      postgres:18.1 >"$destination/database-container.txt"
    ready=false
    for attempt in {1..60}; do
      if docker exec blockless-perf-db pg_isready -h 127.0.0.1 -U postgres -d benchmark >/dev/null 2>&1; then ready=true; break; fi
      sleep 1
    done
    [[ "$ready" == true ]]
    java -Xms512m -Xmx512m -XX:ActiveProcessorCount=2 \
      -jar "$root/$variant/target/blockless-spring-grpc-example-0.1.0-SNAPSHOT.jar" \
      --spring.datasource.hikari.maximum-pool-size=10 >"$destination/application.log" 2>&1 &
    app_pid=$!
    ready=false
    for attempt in {1..120}; do
      kill -0 "$app_pid"
      if grep -q 'Seeded 400 products' "$destination/application.log"; then ready=true; break; fi
      sleep 1
    done
    [[ "$ready" == true ]]
    python3 "$root/benchmarks/run.py" --proto "$results/greeting.proto" --output "$destination"
  done
done
