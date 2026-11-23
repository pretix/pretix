// Member 3 performance workload: authenticated API read of one order (used by both W1 and W2).
//
// Limits were fixed in Documents/Member3-Plan.md section 8 BEFORE the first measured run:
//   1 VU : p95 <= 300 ms, unexpected failures < 1 %
//   5 VU : p95 <= 800 ms, unexpected failures < 1 %
//
// Run from the repository root (server started with: sqe\windows.ps1 serve-perf):
//   k6 run -e VUS=1 --summary-export local/sqe/evidence/perf/run-1vu-a.json src/tests/team/perf/order-read.k6.js
import http from 'k6/http';
import { check, sleep } from 'k6';
import { Rate } from 'k6/metrics';

const VUS = Number(__ENV.VUS || 1);
const P95_LIMIT_MS = { 1: 300, 5: 800 }[VUS];
if (!P95_LIMIT_MS) throw new Error('VUS must be 1 or 5; limits are only defined for those workloads.');

const fixtures = JSON.parse(open(__ENV.FIXTURES || '../../../../local/sqe/windows/fixtures.json'));
const BASE_URL = __ENV.BASE_URL || fixtures.baseUrl;
const CODE = fixtures.orders.m3_perf;
const URL = `${BASE_URL}/api/v1/organizers/${fixtures.organizer}/events/${fixtures.event}/orders/${CODE}/`;
const PARAMS = { headers: { Authorization: `Token ${fixtures.roles.viewer.token}` }, tags: { name: 'GET order' } };

export const unexpected_failures = new Rate('unexpected_failures');

const WARMUP = '15s';
const MEASURE = '75s'; // > 60 s at the full number of users

export const options = {
    scenarios: {
        warmup: { executor: 'constant-vus', vus: VUS, duration: WARMUP, tags: { phase: 'warmup' } },
        measure: { executor: 'constant-vus', vus: VUS, duration: MEASURE, startTime: WARMUP, tags: { phase: 'measure' } },
    },
    thresholds: {
        'http_req_duration{phase:measure}': [`p(95)<=${P95_LIMIT_MS}`],
        'unexpected_failures{phase:measure}': ['rate<0.01'],
        'http_reqs{phase:measure}': ['count>0'],
    },
    summaryTrendStats: ['avg', 'min', 'med', 'p(90)', 'p(95)', 'p(99)', 'max'],
};

export default function () {
    const response = http.get(URL, PARAMS);
    let ok = false;
    try {
        ok = response.status === 200
            && String(response.headers['Content-Type']).startsWith('application/json')
            && response.json('code') === CODE;
    } catch (e) {
        ok = false;
    }
    unexpected_failures.add(!ok);
    check(response, { 'status 200, JSON, same order code': () => ok });
    sleep(1); // think time: a manager reading the order
}
