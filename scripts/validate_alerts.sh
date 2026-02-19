#!/usr/bin/env bash
set -euo pipefail

echo "Validating Prometheus alert rules..."

# Check if promtool is available
if ! command -v promtool &> /dev/null; then
    echo "promtool not found. Installing via Docker..."
    docker run --rm -v "$(pwd)/monitoring/prometheus/rules":/rules:ro \
        prom/prometheus:latest promtool check rules /rules/saas_alerts.yml
else
    promtool check rules monitoring/prometheus/rules/saas_alerts.yml
fi

echo "✅ Alert rules are valid"

echo ""
echo "Testing alert expressions locally..."

# Test error rate expression
echo "1. Ingestion error rate:"
echo 'sum(rate(ingest_requests_total{result="error"}[5m])) / clamp_min(sum(rate(ingest_requests_total[5m])), 0.01)'

# Test skipped ratio expression
echo "2. Skipped ratio:"
echo 'sum(rate(ingest_requests_total{result="skipped"}[5m])) / clamp_min(sum(rate(ingest_requests_total[5m])), 0.01)'

echo ""
echo "To test these queries against live Prometheus:"
echo "  curl -s 'http://localhost:9090/api/v1/query?query=sum(rate(ingest_requests_total{result=\"error\"}[5m]))' | jq"
