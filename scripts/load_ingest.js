iXmport http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
  vus: __ENV.K6_VUS ? parseInt(__ENV.K6_VUS) : 20,
  duration: __ENV.K6_DURATION || '30s',
  thresholds: {
    http_req_failed: ['rate<0.01'],
    http_req_duration: ['p(95)<500'],
  },
};

const TARGET = __ENV.TARGET || 'http://127.0.0.1:8000';

export default function () {
  const matchId = `${__VU}-${__ITER}-${Date.now()}`;
  const payload = JSON.stringify({ rows: [{ match_id: matchId, prob: 0.5 }] });
  const params = { headers: { 'Content-Type': 'application/json' } };
  const res = http.post(`${TARGET}/ingest`, payload, params);

  check(res, {
    'status is 200': (r) => r.status === 200,
    'has persisted or error': (r) => {
      try {
        const b = r.json ? r.json() : JSON.parse(r.body);
        return b && ('persisted' in b || 'error' in b);
      } catch (e) {
        return false;
      }
    },
  });

  sleep(0.05);
}

