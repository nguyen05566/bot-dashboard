#!/usr/bin/env python3
"""
collect.py — Thu thập trạng thái bot fleet (GitHub Actions) rồi ghi data/status.json
Chạy trong GitHub Actions (cron) — đây chính là nơi "Python server-side" hoạt động
cho một trang GitHub Pages (Pages chỉ phục vụ file tĩnh).

Env:
  GH_TOKEN / GITHUB_TOKEN : token đọc API GitHub
  REPOS                  : "owner/reo1,owner/reo2" (mặc định: danh sách dưới)
"""
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

API = "https://api.github.com"
DEFAULT_REPOS = "nguyen05566/jieqi-core,nguyen05566/the-anh,nguyen05566/vht"
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
TOKEN = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or ""
REPOS = [r.strip() for r in os.environ.get("REPOS", DEFAULT_REPOS).split(",") if r.strip()]

HEADERS = {
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
    "User-Agent": "bot-dashboard",
}
if TOKEN:
    HEADERS["Authorization"] = f"Bearer {TOKEN}"


def api(path, accept=None):
    h = dict(HEADERS)
    if accept:
        h["Accept"] = accept
    req = urllib.request.Request(API + path, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=45) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        if e.code in (403, 404):
            return None
        raise
    except Exception:
        return None


def fetch_log(repo, run_id):
    """Tải log job đầu tiên của run (text)."""
    h = dict(HEADERS)
    req = urllib.request.Request(f"{API}/repos/{repo}/actions/runs/{run_id}/logs", headers=h)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.read().decode("utf-8", "replace")
    except Exception:
        return ""


def parse_log(text):
    """Rút thống kê từ log bot."""
    st = {
        "claims_ok": len(re.findall(r"✅ OK \+", text)),
        "transfers": len(re.findall(r"đang chuyển về", text)),
        "idle_breaks": len(re.findall(r"😴", text)),
        "errors": len(re.findall(r"❌|Traceback|CRITICAL", text)),
        "dest_ids": sorted(set(re.findall(r"đang chuyển về (\d+)", text))),
        "idle_seconds": sorted(int(x) for x in re.findall(r"nghỉ (\d+)s", text)),
        "summary": "",
        "last_activity": "",
    }
    m = re.findall(r"TỔNG KẾT:.*", text)
    if m:
        st["summary"] = m[-1].strip()
    m = re.findall(r"\[Claim #(\d+)\]", text)
    if m:
        st["last_claim_no"] = int(m[-1])
    m = re.findall(r"^(\d{4}-\d{2}-\d{2}T[\d:.]+Z)", text, re.M)
    if m:
        st["last_activity"] = m[-1]
    if st["idle_seconds"]:
        st["idle_avg"] = round(sum(st["idle_seconds"]) / len(st["idle_seconds"]), 1)
        st["idle_min"] = min(st["idle_seconds"])
        st["idle_max"] = max(st["idle_seconds"])
    return st


def collect():
    out = {"generated_at": datetime.now(timezone.utc).isoformat(), "repos": {}}
    for repo in REPOS:
        runs = api(f"/repos/{repo}/actions/runs?per_page=30")
        if not runs:
            out["repos"][repo] = {"error": "không đọc được runs"}
            continue
        items = runs.get("workflow_runs", [])
        # gom theo workflow: ưu tiên run đang chạy, else run completed gần nhất
        by_wf = {}
        for r in items:
            wf = r.get("name", "?")
            cur = by_wf.get(wf)
            if cur is None:
                by_wf[wf] = r
            else:
                # ưu tiên in_progress
                if r.get("status") == "in_progress" and cur.get("status") != "in_progress":
                    by_wf[wf] = r
        repo_info = {"total": len(items), "in_progress": 0, "workflows": {}}
        for wf, r in sorted(by_wf.items()):
            status = r.get("status")
            if status == "in_progress":
                repo_info["in_progress"] += 1
            entry = {
                "run_id": r.get("id"),
                "status": status,
                "conclusion": r.get("conclusion"),
                "event": r.get("event"),
                "created_at": r.get("created_at"),
                "updated_at": r.get("updated_at"),
                "url": r.get("html_url"),
            }
            # lấy log của run completed gần nhất (bỏ qua run quá cũ > 36h)
            if status == "completed" and r.get("updated_at"):
                try:
                    age = (datetime.now(timezone.utc) -
                           datetime.fromisoformat(r["updated_at"].replace("Z", "+00:00"))).total_seconds()
                except Exception:
                    age = 1e9
                if age < 36 * 3600:
                    entry["stats"] = parse_log(fetch_log(repo, r["id"]))
            repo_info["workflows"][wf] = entry
        out["repos"][repo] = repo_info
    return out


def update_history(status):
    """Cộng dồn lịch sử để vẽ biểu đồ."""
    os.makedirs(DATA_DIR, exist_ok=True)
    path = os.path.join(DATA_DIR, "history.json")
    hist = []
    if os.path.exists(path):
        try:
            hist = json.load(open(path, encoding="utf-8"))
        except Exception:
            hist = []
    point = {
        "t": status["generated_at"],
        "runs": sum(r.get("in_progress", 0) for r in status["repos"].values()),
        "claims": sum(w.get("stats", {}).get("claims_ok", 0)
                      for r in status["repos"].values() for w in r.get("workflows", {}).values()),
        "transfers": sum(w.get("stats", {}).get("transfers", 0)
                         for r in status["repos"].values() for w in r.get("workflows", {}).values()),
        "errors": sum(w.get("stats", {}).get("errors", 0)
                      for r in status["repos"].values() for w in r.get("workflows", {}).values()),
    }
    hist.append(point)
    # giữ 500 điểm gần nhất
    hist = hist[-500:]
    json.dump(hist, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return point


def main():
    status = collect()
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(os.path.join(DATA_DIR, "status.json"), "w", encoding="utf-8") as f:
        json.dump(status, f, ensure_ascii=False, indent=1)
    point = update_history(status)
    print(json.dumps({"generated_at": status["generated_at"], "point": point}, ensure_ascii=False))
    total_ip = sum(r.get("in_progress", 0) for r in status["repos"].values())
    total_wf = sum(len(r.get("workflows", {})) for r in status["repos"].values())
    print(f"[collect] {total_ip} run đang chạy / {total_wf} workflow theo dõi")
    return 0


if __name__ == "__main__":
    sys.exit(main())
