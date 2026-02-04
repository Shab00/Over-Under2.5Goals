# Developer quick checks

Start dev server (background):
```
make run
```

Check /metrics (after hitting the API to generate traffic):
```
curl -s http://127.0.0.1:8000/metrics | head -n 40
```

Run smoke test (uses data/deliveries.db):
```
make smoke
```

View logs:
```
make logs
```

Stop server:
```
make stop
```
