#!/usr/bin/env bash
set -euo pipefail
# Robust smoke test that runs entirely inside a docker network (no host port binding by default).
# Services:
#  - mock-receiver (mock webhook receiver)
#  - mock-app (optional app metrics)
#  - alertmanager (configured to send to mock-receiver)
#  - prometheus (scrapes alertmanager and mock-receiver)
#
# Exits non-zero if alertmanager_webhook_deliveries_total is not incremented.
#
# Useful environment variables:
#  WAIT_SEC - seconds to wait after posting alert before querying Prometheus (default 20)
#  NETWORK  - docker network name (default smoke_net)

NETWORK="${NETWORK:-smoke_net}"
TMPDIR="$(pwd)/monitoring/ci/.tmp"
WAIT_SEC="${WAIT_SEC:-20}"

cleanup() {
  echo "Cleaning up containers and network..."
  docker rm -f smoke_prometheus smoke_alertmanager mock-receiver mock-app >/dev/null 2>&1 || true
  docker network rm "${NETWORK}" >/dev/null 2>&1 || true
}
dump_debug() {
  echo "==== CONTAINER STATUS ===="
  docker ps -a --filter "name=mock-receiver" --filter "name=mock-app" --filter "name=smoke_alertmanager" --filter "name=smoke_prometheus" --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}' || true
  echo "==== mock-receiver logs ===="
  docker logs mock-receiver --tail 200 || true
  echo "==== mock-app logs ===="
  docker logs mock-app --tail 200 || true
  echo "==== alertmanager logs ===="
  docker logs smoke_alertmanager --tail 200 || true
  echo "==== prometheus logs ===="
  docker logs smoke_prometheus --tail 200 || true
  echo "==== prometheus targets ===="
  docker run --rm --network "${NETWORK}" curlimages/curl:latest -s 'http://smoke_prometheus:9090/api/v1/targets' | jq '.data.activeTargets[] | {job:.labels.job, instance:.labels.instance, health:.health, lastError:.lastError}' || true
}

# ensure cleanup on exit
trap cleanup EXIT

mkdir -p "${TMPDIR}"
echo "Creating network ${NETWORK}..."
docker network create "${NETWORK}" >/dev/null 2>&1 || true

echo "Starting mock receiver..."
docker run -d --name mock-receiver --network "${NETWORK}" \
  -v "$(pwd)":/workdir:ro python:3.12-slim \
  bash -c "python3 /workdir/monitoring/ci/alertmanager_webhook_receiver.py --port 9000"

echo "Starting mock app metrics..."
docker run -d --name mock-app --network "${NETWORK}" \
  -v "$(pwd)":/workdir:ro python:3.12-slim \
  bash -c "python3 /workdir/monitoring/ci/mock_app_metrics.py --port 8000"

echo "Starting Alertmanager (internal network)..."
docker run -d --name smoke_alertmanager --network "${NETWORK}" \
  -v "$(pwd)/monitoring/ci/alertmanager-ci.yml":/etc/alertmanager/alertmanager.yml:ro \
  prom/alertmanager:latest --config.file=/etc/alertmanager/alertmanager.yml

echo "Starting Prometheus (internal network)..."
docker run -d --name smoke_prometheus --network "${NETWORK}" \
  -v "$(pwd)/monitoring/prometheus/prometheus-ci.yml":/etc/prometheus/prometheus.yml:ro \
  prom/prometheus:latest

echo "Waiting for Prometheus to be healthy (inside network)..."
for i in $(seq 1 30); do
  if docker run --rm --network "${NETWORK}" curlimages/curl:latest -sS "http://smoke_prometheus:9090/-/healthy" >/dev/null 2>&1; then
    echo "Prometheus is healthy"
    break
  fi
  sleep 1
done

echo "Posting v2 alert to Alertmanager..."
docker run --rm --network "${NETWORK}" curlimages/curl:latest -s -XPOST -H "Content-Type: application/json" \
  --data '[{"labels":{"alertname":"SmokeTestAlert","severity":"critical"},"annotations":{"summary":"CI smoke test"}}]' \
  "http://smoke_alertmanager:9093/api/v2/alerts" >/dev/null || {
    echo "Failed to POST alert to Alertmanager"
    dump_debug
    exit 2
  }

echo "Waiting ${WAIT_SEC}s for delivery and Prometheus scrape..."
sleep "${WAIT_SEC}"

echo "Querying Prometheus for alertmanager_webhook_deliveries_total..."
COUNT=$(docker run --rm --network "${NETWORK}" curlimages/curl:latest -s "http://smoke_prometheus:9090/api/v1/query?query=alertmanager_webhook_deliveries_total" \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d.get('data',{}).get('result',[])) and int(float(d['data']['result'][0]['value'][1])) or 0)")

echo "Deliveries seen by Prometheus: ${COUNT}"
if [ "${COUNT}" -lt 1 ]; then
  echo "SMOKE TEST FAILED: alertmanager_webhook_deliveries_total < 1"
  dump_debug
  exit 2
fi

echo "SMOKE TEST PASSED"
exit 0
