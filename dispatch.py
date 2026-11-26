#!/usr/bin/env python3
"""Dispatch the signing workflow, print the upterm SSH command, then the OTA link.

Usage:
    export GH_TOKEN=your_new_token
    python3 dispatch.py
"""
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

TOKEN = os.environ.get("GH_TOKEN")
if not TOKEN:
    sys.exit("Set GH_TOKEN first:  export GH_TOKEN=your_new_token")

REPO = "quickhaven67/sign-LiveContainer"
WF = "sign-livecontainer.yml"  # must match the filename in .github/workflows/
GIST_ID = "a780f323dcc1db7243c296f4997f43e9"
API = "https://api.github.com"
HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Accept": "application/vnd.github+json",
    "User-Agent": "ish",
}


def api(path, method="GET", data=None):
    hdrs = dict(HEADERS)
    body = None
    if data is not None:
        hdrs["Content-Type"] = "application/json"
        body = json.dumps(data).encode("utf-8")
    req = urllib.request.Request(API + path, data=body, method=method, headers=hdrs)
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read().decode("utf-8", errors="ignore")
        return json.loads(raw) if raw.strip() else {}


def parse_time(s):
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def find_run(started):
    """Newest workflow_dispatch run created after `started`."""
    for _ in range(20):
        time.sleep(3)
        runs = api(
            f"/repos/{REPO}/actions/workflows/{WF}/runs?event=workflow_dispatch&per_page=5"
        ).get("workflow_runs", [])
        for r in runs:
            if parse_time(r["created_at"]) >= started - timedelta(seconds=5):
                return r
    raise RuntimeError("Could not find the dispatched run")


def gist_files():
    return api(f"/gists/{GIST_ID}").get("files", {})


def main():
    branch = api(f"/repos/{REPO}")["default_branch"]
    started = datetime.now(timezone.utc)
    api(
        f"/repos/{REPO}/actions/workflows/{WF}/dispatches",
        method="POST",
        data={"ref": branch, "inputs": {"ssh_before_auth": "true", "debug_upterm": "true"}},
    )
    run = find_run(started)
    rid = run["id"]
    print("Run ID:", rid)
    print("URL:", run.get("html_url", ""), flush=True)

    shown_ssh = False
    while True:
        st = api(f"/repos/{REPO}/actions/runs/{rid}")
        print("Status:", st.get("status"), st.get("conclusion") or "", flush=True)

        if not shown_ssh:
            f = gist_files().get("upterm_ssh.txt")
            if f and f"run {rid}" in f.get("content", ""):
                print("\n" + f["content"], flush=True)
                shown_ssh = True

        if st.get("status") == "completed":
            break
        time.sleep(10)

    if st.get("conclusion") == "success":
        m = gist_files().get("manifest.plist")
        if m:
            itms = "itms-services://?action=download-manifest&url=" + urllib.parse.quote(
                m["raw_url"], safe=""
            )
            print("\nGIST_RAW_URL=" + m["raw_url"])
            print("ITMS_URL=" + itms)
    else:
        print("Run did not succeed. Check the run URL for logs.")


if __name__ == "__main__":
    try:
        main()
    except urllib.error.HTTPError as e:
        print("HTTP Error:", e.code, e.reason)
        print(e.read().decode("utf-8", errors="ignore")[:500])
    except KeyboardInterrupt:
        print("\nStopped watching (the workflow keeps running on GitHub).")
    except Exception as e:
        print("Error:", type(e).__name__, e)
