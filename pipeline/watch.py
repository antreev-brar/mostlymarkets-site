"""Watch the market for one Actions job: refresh, detect, save, deploy, then sleep to the next slot and repeat.

GitHub drops most scheduled runs of a busy cron, so data.yml no longer relies on one run per slot. Each run loops
inside a single job for up to ~5.5 hours and, when its time is up mid-session, dispatches its own successor.
The crons in data.yml are only starters and backups.

Slots (New York time):
- weekdays 06:00-19:45: every 15 minutes
- weekdays 20:30-23:30: hourly at :30
- otherwise (overnight, weekends): one pass per run, then exit

  python3 pipeline/watch.py            # loop (what data.yml runs)
  python3 pipeline/watch.py --once     # one pass, no sleeping
  python3 pipeline/watch.py --slots 2026-10-30T19:50   # print the next slots after that time (testing)
"""
from __future__ import annotations

import datetime as dt
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import marketdata as md  # noqa: E402

ROOT = md.ROOT
BUDGET = dt.timedelta(minutes=320)  # don't start a pass after this; the job's timeout is 355 minutes
REACH = dt.timedelta(minutes=65)    # stay alive only if the next slot is this close


def is_slot(t: dt.datetime) -> bool:
    if t.weekday() >= 5:
        return False
    if 6 <= t.hour < 20:
        return t.minute % 15 == 0
    return t.hour >= 20 and t.minute == 30


def next_slot(now: dt.datetime) -> dt.datetime | None:
    t = now.replace(second=0, microsecond=0) + dt.timedelta(minutes=1)
    while t - now <= REACH:
        if is_slot(t):
            return t
        t += dt.timedelta(minutes=1)
    return None


def sh(args: list[str], **kw) -> bool:
    print("$ " + " ".join(args), flush=True)
    r = subprocess.run(args, cwd=ROOT, **kw)
    if r.returncode:
        print(f"::warning::{' '.join(args)} exited {r.returncode}", flush=True)
    return r.returncode == 0


def wake_writer() -> None:
    url, token = os.environ.get("FIRE_URL"), os.environ.get("FIRE_TOKEN")
    if not (url and token):
        print("no routine token set; the scheduled writer runs will pick these up")
        return
    at = md.now_et().strftime("%H:%M ET")
    body = json.dumps({"text": f"Urgent events were queued at {at}. Follow pipeline/WRITER.md now."}).encode()
    req = urllib.request.Request(url, data=body, method="POST", headers={
        "Authorization": f"Bearer {token}", "anthropic-version": "2026-10-21", "Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=30).read()
        print("woke the writer")
    except Exception as e:  # noqa: BLE001
        print(f"::warning::waking the writer failed: {e}")


def one_pass() -> None:
    sh(["git", "pull", "--rebase", "-q", "origin", "main"])
    if not sh([sys.executable, "pipeline/refresh.py"]):
        print("::warning::refresh failed; skipping this pass (nothing saved)")
        return
    with tempfile.NamedTemporaryFile("r", suffix=".out") as out:
        sh([sys.executable, "pipeline/detect.py"], env={**os.environ, "GITHUB_OUTPUT": out.name})
        flags = dict(line.strip().split("=", 1) for line in out if "=" in line)
    sh(["bash", "pipeline/data_push.sh"])
    sh(["git", "add", "events"])
    if subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=ROOT).returncode:
        sh(["git", "commit", "-q", "-m", f"events: {md.now_et():%Y-%m-%d %H:%M} ET"])
        for _ in range(3):
            if sh(["git", "pull", "--rebase", "-q", "origin", "main"]) and sh(["git", "push", "-q", "origin", "HEAD:main"]):
                break
            time.sleep(5)
    if flags.get("wake") == "true":
        wake_writer()
    # build.yml rebuilds and deploys the site with the fresh data (its own concurrency group keeps deploys in order).
    sh(["gh", "workflow", "run", "build.yml", "--ref", "main"])


def main(argv: list[str]) -> None:
    if "--slots" in argv:
        t = dt.datetime.fromisoformat(argv[argv.index("--slots") + 1]).replace(tzinfo=md.ET)
        for _ in range(6):
            t = next_slot(t)
            print(t or "none within reach: exit")
            if not t:
                break
        return
    start = md.now_et()
    while True:
        print(f"::group::pass at {md.now_et():%Y-%m-%d %H:%M:%S} ET", flush=True)
        one_pass()
        print("::endgroup::", flush=True)
        now = md.now_et()
        nxt = next_slot(now)
        if "--once" in argv or nxt is None:
            print("no slot within reach; done")
            return
        if nxt - start > BUDGET:
            # Out of time mid-session: queue a successor. It waits in the concurrency group until this run ends.
            if os.environ.get("MM_ENABLED") == "true":
                sh(["gh", "workflow", "run", "data.yml", "--ref", "main"])
            print("time budget used; handed over to the next run")
            return
        wait = (nxt - md.now_et()).total_seconds()
        print(f"next pass at {nxt:%H:%M} ET (sleeping {wait / 60:.1f} min)", flush=True)
        time.sleep(max(0.0, wait))


if __name__ == "__main__":
    main(sys.argv[1:])
