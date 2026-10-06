"""
Benchmark: sidebar rendering + full Postman import flow with many requests.

Usage (from repo root):
    PYTHONPATH=. python tests/bench_sidebar_import.py [--limit SECONDS]

Uses a temporary ProfileManager dir (never touches real profiles).
Prints timings and exits non-zero if any case exceeds --limit (default 15s).
Needs a display. If the UI hangs, kill the process from the caller
(e.g. run in background and `kill -9` after a deadline).
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys
import tempfile
import time

import customtkinter as ctk

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from app.core.postman_importer import parse_postman_file
from app.core.profile_manager import ProfileManager
from app.models.request_model import RequestProfile
from app.ui.postman_import_dialog import PostmanImportDialog
from app.ui.sidebar import Sidebar

SAMPLE = os.path.join(ROOT, "tests", "btpns.postman_collection.json")
RESULTS: list[tuple[str, float]] = []


def timed(label: str, fn):
    t = time.perf_counter()
    out = fn()
    dt = time.perf_counter() - t
    RESULTS.append((label, dt))
    print(f"{label:<58s} {dt:7.2f}s", flush=True)
    return out


def synthetic(n: int, per_collection: int) -> list[RequestProfile]:
    methods = ["GET", "POST", "PUT", "DELETE", "PATCH"]
    return [
        RequestProfile(
            name=f"Request number {i} with a reasonably long descriptive name",
            url=f"https://example.com/api/v1/items/{i}",
            method=methods[i % len(methods)],
            collection=f"Collection {i // per_collection:03d}",
        )
        for i in range(n)
    ]


def fresh_pm(profiles: list[RequestProfile]) -> tuple[ProfileManager, str]:
    d = tempfile.mkdtemp(prefix="kp_bench_")
    pm = ProfileManager(d)
    for p in profiles:
        pm.save_profile(p)
    return pm, d


def build_sidebar(root, pm) -> Sidebar:
    sb = Sidebar(root, pm)
    sb.pack(side="left", fill="y")
    root.update()
    return sb


def bench_sidebar(root, label: str, profiles: list[RequestProfile]) -> None:
    pm, d = fresh_pm(profiles)
    try:
        sb = timed(f"sidebar build+render  {label}", lambda: build_sidebar(root, pm))
        timed(f"  refresh() expanded     {label}", lambda: (sb.refresh(), root.update()))
        cols = list(pm.get_profiles_by_collection())

        def collapse_all():
            for c in cols:
                sb._collapsed[c] = True
            sb.refresh()
            root.update()

        def expand_all():
            for c in cols:
                sb._collapsed[c] = False
            sb.refresh()
            root.update()

        timed(f"  collapse all           {label}", collapse_all)
        timed(f"  expand all             {label}", expand_all)
        timed(f"  search filter 'request number 1' {label}", lambda: (sb._search_var.set("request number 1"), root.update()))
        sb._search_var.set("")
        root.update()
        sb.destroy()
    finally:
        shutil.rmtree(d, ignore_errors=True)


def bench_import(root) -> None:
    result = timed("parse sample file", lambda: parse_postman_file(SAMPLE))
    n = len(result.profiles)
    pm, d = fresh_pm([])
    try:
        sb = build_sidebar(root, pm)
        done: list = []

        def run():
            dlg = PostmanImportDialog(
                root, SAMPLE, result, pm,
                on_import_done=lambda c, t: (done.append((c, t)), sb.refresh()),
            )
            root.update()
            dlg._select_all(True)
            dlg._do_import()
            root.update()

        timed(f"full import flow (dialog+import+sidebar) {n} reqs", run)
        assert done and done[0][0] == n, f"import count mismatch: {done}"
        sb.destroy()
    finally:
        shutil.rmtree(d, ignore_errors=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=float, default=15.0, help="max seconds per case")
    ap.add_argument("--skip-sample", action="store_true")
    args = ap.parse_args()

    root = ctk.CTk()
    root.geometry("1000x700")
    root.update()

    for n in (50, 100, 616):
        bench_sidebar(root, f"{n} profiles/{max(1, n // 5)} collections", synthetic(n, 5))
    bench_sidebar(root, "616 profiles/1 collection", synthetic(616, 616))
    bench_sidebar(root, "2000 profiles/400 collections", synthetic(2000, 5))
    bench_sidebar(root, "2000 profiles/1 collection", synthetic(2000, 2000))

    if not args.skip_sample and os.path.exists(SAMPLE):
        r = parse_postman_file(SAMPLE)
        ncol = len({p.collection for p in r.profiles})
        bench_sidebar(root, f"sample {len(r.profiles)} profiles/{ncol} collections (real)", r.profiles)
        bench_import(root)

    root.destroy()
    worst = max(RESULTS, key=lambda x: x[1])
    print(f"\nworst case: {worst[0].strip()} = {worst[1]:.2f}s (limit {args.limit}s)")
    return 1 if worst[1] > args.limit else 0


if __name__ == "__main__":
    sys.exit(main())
