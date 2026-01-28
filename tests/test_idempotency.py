from fastapi.testclient import TestClient
import sqlite3
from src.api.main import APP

client = TestClient(APP)
HEADERS = {"Content-Type": "application/json", "X-API-KEY": "choose-a-secret"}

def test_idempotency_smoke():
    mid = 1_234_567_890

    r1 = client.post("/ingest", json={"rows":[{"match_id": mid, "prob": 0.5}], "source": "it-test-1"}, headers=HEADERS)
    assert r1.status_code == 200
    assert r1.json().get("persisted", 0) == 1

    r2 = client.post("/ingest", json={"rows":[{"match_id": mid, "prob": 0.6}], "source": "it-test-2"}, headers=HEADERS)
    assert r2.status_code == 200
    assert r2.json().get("persisted", 0) == 0

    conn = sqlite3.connect("data/deliveries.db")
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM deliveries WHERE match_id = ?", (mid,))
    assert cur.fetchone()[0] == 1
    conn.close()
