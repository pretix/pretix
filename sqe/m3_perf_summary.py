"""Summarise the four k6 runs from their raw per-request output, restricted to the measured phase.

k6's own `{phase:measure}` rate divides by the whole run (warm-up included), so throughput is recomputed
here as measured requests / 75 s. p95 uses linear interpolation (the same method as k6) and is printed next
to k6's value as a cross-check.

Usage: python sqe/m3_perf_summary.py <evidence dir with run-*.raw.json and run-*.summary.json>
"""
import json
import math
import sys
from pathlib import Path

MEASURE_SECONDS = 75
RUNS = [('1vu-a', 1, 300), ('1vu-b', 1, 300), ('5vu-a', 5, 800), ('5vu-b', 5, 800)]


def percentile(sorted_values, p):
    k = (len(sorted_values) - 1) * p
    lo, hi = math.floor(k), math.ceil(k)
    return sorted_values[lo] + (sorted_values[hi] - sorted_values[lo]) * (k - lo)


def summarise(directory, run, vus, limit):
    durations, failures, checked = [], 0, 0
    with open(directory / f'run-{run}.raw.json', encoding='utf-8') as raw:
        for line in raw:
            point = json.loads(line)
            if point.get('type') != 'Point' or point['data'].get('tags', {}).get('phase') != 'measure':
                continue
            if point['metric'] == 'http_req_duration':
                durations.append(point['data']['value'])
            elif point['metric'] == 'unexpected_failures':
                checked += 1
                failures += point['data']['value']
    durations.sort()
    k6 = json.loads((directory / f'run-{run}.summary.json').read_text(encoding='utf-8'))['metrics']
    p95_k6 = k6['http_req_duration{phase:measure}']['p(95)']
    fail_pct = 100 * failures / checked
    return {
        'run': run, 'vus': vus, 'requests': len(durations),
        'p95_ms': round(percentile(durations, 0.95), 1), 'p95_k6_ms': round(p95_k6, 1),
        'median_ms': round(percentile(durations, 0.5), 1), 'max_ms': round(durations[-1], 1),
        'req_per_s': round(len(durations) / MEASURE_SECONDS, 2), 'unexpected_fail_pct': round(fail_pct, 2),
        'p95_limit_ms': limit, 'pass': p95_k6 <= limit and fail_pct < 1,
    }


def main(directory):
    rows = [summarise(directory, *run) for run in RUNS]
    (directory / 'results.json').write_text(json.dumps(rows, indent=2) + '\n', encoding='utf-8')
    print('| Run | VUs | Requests | p95 ms (k6) | Median ms | Max ms | Requests/s | Unexpected failures | p95 limit | Verdict |')
    print('|---|---|---|---|---|---|---|---|---|---|')
    for r in rows:
        print(f"| {r['run']} | {r['vus']} | {r['requests']} | {r['p95_ms']} ({r['p95_k6_ms']}) | {r['median_ms']} | "
              f"{r['max_ms']} | {r['req_per_s']} | {r['unexpected_fail_pct']} % | {r['p95_limit_ms']} | "
              f"{'PASS' if r['pass'] else 'FAIL'} |")


if __name__ == '__main__':
    main(Path(sys.argv[1]))
