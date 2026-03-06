from time import time
from fastapi import Response, FastAPI, Request

try:
    from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
    _HAS_PROM = True
except Exception:
    _HAS_PROM = False

    def generate_latest():
        return b""

    CONTENT_TYPE_LATEST = "text/plain; version=0.0.4; charset=utf-8"

    class _NoopMetric:
        def __init__(self, *args, **kwargs):
            pass

        def labels(self, *a, **k):
            return self

        def inc(self, n=1):
            # no-op
            return None

        def observe(self, v):
            # no-op
            return None

    Counter = _NoopMetric
    Histogram = _NoopMetric

HTTP_REQUESTS = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "http_status"],
)

HTTP_REQUEST_DURATION = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency (seconds)",
    ["endpoint"],
)

INGESTION_COUNTER = Counter(
    "ingest_requests_total",
    "Total ingestion requests processed",
    ["result", "source"],
)

SMOKE_TEST_RUNS = Counter(
    "smoke_test_runs_total",
    "Total smoke test runs (lightweight health checks)",
    ["kind", "result"],
)

async def metrics_endpoint() -> Response:
    # Return empty body when prometheus_client missing, otherwise return generate_latest()
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


def add_prometheus_metrics(app: FastAPI) -> None:
    """
    Add lightweight Prometheus middleware and /metrics endpoint.
    Works whether prometheus_client is installed or not.
    """
    @app.middleware("http")
    async def prometheus_middleware(request: Request, call_next):
        path = request.url.path or "/"
        if path == "/metrics":
            return await call_next(request)

        start = time()
        response = await call_next(request)
        req_time = time() - start

        try:
            HTTP_REQUEST_DURATION.labels(endpoint=path).observe(req_time)
        except Exception:
            pass

        try:
            HTTP_REQUESTS.labels(
                method=request.method,
                endpoint=path,
                http_status=str(response.status_code),
            ).inc()
        except Exception:
            pass

        return response

    app.add_api_route("/metrics", metrics_endpoint)
