#!/usr/bin/env bash
set -euo pipefail

RUN_ID="${RUN_ID:-$$}"
NETWORK="${NETWORK:-smoke_net_${RUN_ID}}"
TMPDIR="$(pwd)/monitoring/ci/.tmp"
WAIT_SEC="${WAIT_SEC:-20}"
ARTIFACT_DIR="${ARTIFACT_DIR:-}"
SKIP_CLEANUP="${SKIP_CLEANUP:-0}"

C_PROM="smoke_prometheus_${RUN_ID}"
C_AM="smoke_alertmanager_${RUN_ID}"
C_RECV="mock-receiver_${RUN_ID}"
C_APP="mock-app_${RUN_ID}"

TEST_PASSED=0

cleanup() {
  if [ "${SKIP_CLEANUP}" = "1" ]; then
    echo "SKIP_CLEANUP=1, leaving containers and network for inspection"
    echo "  NETWORK=${NETWORK}"
    echo "  Containers: ${C_PROM} ${C_AM} ${C_RECV} ${C_APP}"
    return
  fi

  echo "Cleaning up containers and network..."
  docker rm -f "${C_PROM}" "${C_AM}" "${C_RECV}" "${C_APP}" >/dev/null 2>&1 || true
  docker network rm "${NETWORK}" >/dev/null 2>&1 || true

  if [ "${TEST_PASSED}" = "1" ] && [ -d "${TMPDIR}" ]; then
    rm -rf "${TMPDIR}"
  fi
}

dump_debug() {
  local target_dir="${1:-}"

  if [ -n "${target_dir}" ]; then
    mkdir -p "${target_dir}"
    echo "Saving debug artifacts to ${target_dir}..."
  fi

  {
    echo "==== SMOKE TEST DEBUG INFO ===="
    echo "Timestamp: $(date -u +"%Y-%m-%d %H:%M:%S UTC")"
    echo "RUN_ID: ${RUN_ID}"
    echo "WAIT_SEC: ${WAIT_SEC}"
    echo "NETWORK: ${NETWORK}"
    echo "Containers: ${C_PROM} ${C_AM} ${C_RECV} ${C_APP}"
    echo ""
    echo "==== CONTAINER STATUS ===="
    docker ps -a --filter "name=${C_RECV}" --filter "name=${C_APP}" \
      --filter "name=${C_AM}" --filter "name=${C_PROM}" \
      --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}' 2>&1 || echo "Failed to get container status"
    echo ""
    echo "==== DOCKER NETWORK INSPECT ===="
    docker network inspect "${NETWORK}" 2>&1 || echo "Network ${NETWORK} not found"
    echo ""
  } | tee ${target_dir:+${target_dir}/smoke-debug-summary.log}

  for container in "${C_RECV}" "${C_APP}" "${C_AM}" "${C_PROM}"; do
    echo "==== ${container} logs ===="
    docker logs "${container}" --tail 500 2>&1 | tee ${target_dir:+${target_dir}/${container}.log} || echo "No logs for ${container}"
    echo ""
  done

  {
    echo "==== PROMETHEUS TARGETS (parsed) ===="
    docker run --rm --network "${NETWORK}" curlimages/curl:latest -s \
      "http://${C_PROM}:9090/api/v1/targets" 2>&1 | \
      docker run --rm -i ghcr.io/jqlang/jq:latest -r \
        '.data.activeTargets[] | {job:.labels.job, instance:.labels.instance, health:.health, lastError:.lastError} | @json' \
        2>&1 || echo "Failed to query/parse Prometheus targets"
  } | tee ${target_dir:+${target_dir}/prometheus-targets.json}

  {
    echo "==== PROMETHEUS METRICS (alertmanager_webhook_*) ===="
    docker run --rm --network "${NETWORK}" curlimages/curl:latest -s \
      "http://${C_PROM}:9090/api/v1/query?query=alertmanager_webhook_deliveries_total" 2>&1 || \
      echo "Failed to query metrics"
  } | tee ${target_dir:+${target_dir}/prometheus-metrics.json}
}

trap cleanup EXIT
mkdir -p "${TMPDIR}"

echo "Ensuring clean state (idempotent pre-cleanup)..."
docker rm -f "${C_PROM}" "${C_AM}" "${C_RECV}" "${C_APP}" >/dev/null 2>&1 || true
docker network rm "${NETWORK}" >/dev/null 2>&1 || true

echo "Creating network ${NETWORK}..."
if ! docker network create "${NETWORK}" >/dev/null 2>&1; then
  echo "Warning: Network might already exist, attempting to continue..."
  if ! docker network inspect "${NETWORK}" >/dev/null 2>&1; then
    echo "ERROR: Failed to create or find network ${NETWORK}"
    exit 1
  fi
fi

echo "Starting mock receiver..."
if ! docker run -d --name "${C_RECV}" --network "${NETWORK}" --network-alias mock-receiver \
  -v "$(pwd)":/workdir:ro python:3.12-slim \
  bash -c "python3 /workdir/monitoring/ci/alertmanager_webhook_receiver.py --port 9000" >/dev/null; then
  echo "ERROR: Failed to start mock receiver"
  dump_debug "${ARTIFACT_DIR}"
  exit 1
fi

echo "Starting mock app metrics..."
if ! docker run -d --name "${C_APP}" --network "${NETWORK}" --network-alias mock-app \
  -v "$(pwd)":/workdir:ro python:3.12-slim \
  bash -c "python3 /workdir/monitoring/ci/mock_app_metrics.py --port 8000" >/dev/null; then
  echo "ERROR: Failed to start mock app metrics"
  dump_debug "${ARTIFACT_DIR}"
  exit 1
fi

echo "Starting Alertmanager (internal network)..."
if ! docker run -d --name "${C_AM}" --network "${NETWORK}" --network-alias alertmanager \
  -v "$(pwd)/monitoring/ci/alertmanager-ci.yml":/etc/alertmanager/alertmanager.yml:ro \
  prom/alertmanager:latest --config.file=/etc/alertmanager/alertmanager.yml >/dev/null; then
  echo "ERROR: Failed to start Alertmanager"
  dump_debug "${ARTIFACT_DIR}"
  exit 1
fi

echo "Starting Prometheus (internal network)..."
if ! docker run -d --name "${C_PROM}" --network "${NETWORK}" \
  -v "$(pwd)/monitoring/prometheus/prometheus-ci.yml":/etc/prometheus/prometheus.yml:ro \
  prom/prometheus:latest >/dev/null; then
  echo "ERROR: Failed to start Prometheus"
  dump_debug "${ARTIFACT_DIR}"
  exit 1
fi

echo "Waiting for Prometheus to be healthy (inside network)..."
for i in $(seq 1 30); do
  if docker run --rm --network "${NETWORK}" curlimages/curl:latest -sS \
    "http://${C_PROM}:9090/-/healthy" >/dev/null 2>&1; then
    echo "Prometheus is healthy (attempt ${i}/30)"
    break
  fi
  if [ "${i}" -eq 30 ]; then
    echo "ERROR: Prometheus failed to become healthy after 30 seconds"
    dump_debug "${ARTIFACT_DIR}"
    exit 1
  fi
  sleep 1
done

echo "Posting v2 alert to Alertmanager..."
if ! docker run --rm --network "${NETWORK}" curlimages/curl:latest -s -XPOST \
  -H "Content-Type: application/json" \
  --data '[{"labels":{"alertname":"SmokeTestAlert","severity":"critical"},"annotations":{"summary":"CI smoke test"}}]' \
  "http://${C_AM}:9093/api/v2/alerts" >/dev/null; then
  echo "ERROR: Failed to POST alert to Alertmanager"
  dump_debug "${ARTIFACT_DIR}"
  exit 2
fi

echo "Waiting ${WAIT_SEC}s for delivery and Prometheus scrape..."
sleep "${WAIT_SEC}"

echo "Querying Prometheus for alertmanager_webhook_deliveries_total..."
COUNT="$(
  docker run --rm --network "${NETWORK}" curlimages/curl:latest -s \
    "http://${C_PROM}:9090/api/v1/query?query=alertmanager_webhook_deliveries_total" | \
  python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d.get('data',{}).get('result',[])) and int(float(d['data']['result'][0]['value'][1])) or 0)" \
  2>/dev/null || echo "0"
)"

echo "Deliveries seen by Prometheus: ${COUNT}"
if [ "${COUNT}" -lt 1 ]; then
  echo "SMOKE TEST FAILED: alertmanager_webhook_deliveries_total < 1"
  dump_debug "${ARTIFACT_DIR}"
  exit 2
fi

TEST_PASSED=1
echo "✅ SMOKE TEST PASSED"
exit 0
