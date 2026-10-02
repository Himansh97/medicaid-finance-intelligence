"""Run with python -m src.runtime.worker [--once]."""
import argparse
import os
import time

from src.runtime import jobs


def run_once(execute=None):
    if execute is None:
        from src.runtime.postgres import execute_fixture
        execute = execute_fixture
    with jobs.connect() as conn:
        job = jobs.claim(conn)
    if job is None:
        return False
    try:
        with jobs.connect() as conn:
            # The whole fixture and publication are one transaction, fenced at commit.
            conn.execute("SET LOCAL statement_timeout = '100s'")
            result = execute(conn, 'run_' + job['id'].hex, job['scenario'])
            jobs.finish(conn, job, result)
    except jobs.LostLease:
        pass
    except Exception:
        # Never persist exception strings: drivers may include credentials or SQL values.
        with jobs.connect() as conn:
            jobs.fail(conn, job)
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--once', action='store_true')
    args = parser.parse_args()
    if os.environ.get('APP_ENV') != 'local':
        raise SystemExit('The M1 runtime requires APP_ENV=local')
    while True:
        run_once()
        if args.once:
            break
        time.sleep(2)


if __name__ == '__main__':
    main()
