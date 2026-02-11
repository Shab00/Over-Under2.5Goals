from prometheus_client import start_http_server, Counter
from flask import Flask, request

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
    start_http_server(9101)
    app.run(host='0.0.0.0', port=8001)
