from time import time
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
from fastapi import Response, FastAPI, Request

# Counts total HTTP requests (labelled by method, endpoint, status)
HTTP_REQUESTS = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "http_status"],
)

# Histogram for request latency
HTTP_REQUEST_DURATION = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency (seconds)",
    ["endpoint"],
)

# Ingestion-specific counter: result in {persisted, skipped, error}, source e.g. api-ingest
INGESTION_COUNTER = Counter(
    "ingest_requests_total",
    "Total ingestion requests processed",
    ["result", "source"],
)


async def metrics_endpoint() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


def add_prometheus_metrics(app: FastAPI) -> None:
    """
    Adds a lightweight Prometheus middleware and /metrics endpoint.
    Keeps labels low-cardinality (endpoint path only).
    """
    @app.middleware("http")
    async def prometheus_middleware(request: Request, call_next):
        path = request.url.path or "/"
        # Avoid instrumenting the /metrics endpoint itself
        if path == "/metrics":
            return await call_next(request)

        start = time()
        response = await call_next(request)
        req_time = time() - start

        # Observe latency (by path)
        try:
            HTTP_REQUEST_DURATION.labels(endpoint=path).observe(req_time)
        except Exception:
            pass

        # Increment requests counter with status
        try:
            HTTP_REQUESTS.labels(
                method=request.method,
                endpoint=path,
                http_status=str(response.status_code),
            ).inc()
        except Exception:
            pass

        return response

    # Expose /metrics
    app.add_api_route("/metrics", metrics_endpoint)
