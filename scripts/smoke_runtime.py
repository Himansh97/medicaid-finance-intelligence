"""Exercise the running local API and worker using synthetic scenarios only."""
import argparse
import json
import time
from urllib.request import Request, urlopen
from uuid import uuid4


def request(base, path, payload=None):
    data = None if payload is None else json.dumps(payload).encode()
    req = Request(base + path, data=data, headers={'Content-Type': 'application/json'})
    with urlopen(req, timeout=10) as response:
        return json.load(response)


def smoke(base):
    assert request(base, '/health/ready')['status'] == 'ready'
    for scenario in ('clean', 'defective'):
        payload = dict(scenario=scenario, idempotency_key='smoke-' + uuid4().hex)
        job = request(base, '/jobs', payload)
        assert request(base, '/jobs', payload)['id'] == job['id']
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            status = request(base, '/jobs/' + job['id'])
            if status['status'] in ('SUCCEEDED', 'FAILED'):
                break
            time.sleep(1)
        assert status['status'] == 'SUCCEEDED', status
        result = request(base, '/runs/' + job['id'])
        assert result['status'] == ('READY_FOR_REVIEW' if scenario == 'clean' else 'FAILED')
        assert request(base, '/runs/' + job['id'] + '/preflight')['eligible_for_submission'] == (scenario == 'clean')
        assert request(base, '/runs/' + job['id'] + '/kpis')
        checks = request(base, '/runs/' + job['id'] + '/quality')
        assert len(checks) == 14
        assert sum(r['disposition'] == 'FAIL' for r in checks) == (0 if scenario == 'clean' else 3)
        print(f"{scenario}: job {job['id']} completed; finance={result['status']}; 14 checks", flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', default='http://127.0.0.1:8000')
    smoke(parser.parse_args().base_url.rstrip('/'))
