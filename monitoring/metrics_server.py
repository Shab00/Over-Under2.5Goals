from prometheus_client import start_http_server, Counter
from flask import Flask, request

# Prometheus metric: counts ingestion outcomes (labels: result)
SUCCESS = Counter('ingest_requests_total', 'Ingest requests', ['result'])

app = Flask(__name__)

@app.route('/inc', methods=['POST'])
def inc():
    data = request.json or {}
    result = data.get('result', 'persisted')
    count = int(data.get('count', 1))
    for _ in range(count):
        SUCCESS.labels(result=result).inc()
    return {"inc": True, "result": result, "count": count}

if __name__ == '__main__':
    # Bind the Prometheus exporter on 0.0.0.0 so Docker containers can scrape via host.docker.internal
    start_http_server(9101, addr="0.0.0.0")
    # Control endpoints (POST /inc) are served by Flask and also bind to all interfaces
    app.run(host='0.0.0.0', port=8001)
