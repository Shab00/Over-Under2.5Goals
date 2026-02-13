from prometheus_client import start_http_server, Counter, Histogram
import random
import time

# Counters for ingest results
ingest_requests_total = Counter('ingest_requests_total', 'Ingest requests by result', ['result'])
# Histogram for latency
ingest_latency_seconds = Histogram('ingest_latency_seconds', 'Ingest request latency seconds', buckets=(0.005,0.01,0.025,0.05,0.1,0.25,0.5,1,2,5))

def simulate_traffic():
    # Randomly increment counters and observe latency
    r = random.random()
    if r < 0.02:
        ingest_requests_total.labels(result="error").inc()
    elif r < 0.20:
        ingest_requests_total.labels(result="skipped").inc()
    else:
        ingest_requests_total.labels(result="success").inc()

    # observe a latency sampled from a distribution
    ingest_latency_seconds.observe(random.expovariate(50))

if __name__ == "__main__":
    # Port matches the target Prometheus has configured (9101 in your up output)
    start_http_server(9101)
    print("Test metrics exporter listening on :9101")
    while True:
        simulate_traffic()
        time.sleep(0.2)
