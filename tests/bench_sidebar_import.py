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
        # Folder structure must be preserved (default root = parsed collection name)
        expected = {p.collection for p in result.profiles}
        got = pm.get_collections()
        assert set(got) == expected and len(got) == len(expected), (len(got), len(expected))
        assert len(pm.load_all_profiles()) == n
        assert len(sb._profile_btns) == n, len(sb._profile_btns)
        print(f"  structure preserved: {len(got)} collections, {n} profiles, sidebar rows {len(sb._profile_btns)}")
        sb.destroy()
    finally:
        shutil.rmtree(d, ignore_errors=True)


class _Settings:
    def get(self, key, default=None):
        return {"default_timeout": 10.0, "proxy_enabled": False}.get(key, default)


def bench_runner_checklist(root, n: int) -> None:
    from app.ui.runner_window import RunnerWindow
    pm, d = fresh_pm(synthetic(n, n))
    try:
        win = timed(f"runner window open (checklist {n} items)",
                    lambda: (lambda w: (root.update(), w)[1])(RunnerWindow(root, pm, _Settings())))
        assert len(win._checklist) == n
        names = [p.name for p, _ in win._checklist]
        assert names == sorted(names, key=str.lower), "checklist order changed"

        def none_all():
            win._select_all(False)
            root.update()
        timed(f"  select none ({n})", none_all)
        assert not any(v.get() for _, v in win._checklist)
        timed(f"  select all ({n})", lambda: (win._select_all(True), root.update()))
        assert all(v.get() for _, v in win._checklist)
        # click-toggle the first row through the real canvas handler
        cl = win._checklist_scroll
        cl._canvas.event_generate("<Motion>", x=40, y=5)
        cl._canvas.event_generate("<ButtonRelease-1>", x=40, y=5)
        root.update()
        assert win._checklist[0][1].get() is False, "click did not toggle first row"
        win.destroy()
    finally:
        shutil.rmtree(d, ignore_errors=True)


def bench_runner_run(root, n: int, deadline: float = 90.0) -> None:
    """Real run against a local dummy HTTP server; checks counters/results."""
    import http.server
    import threading
    from app.ui.runner_window import RunnerWindow

    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            body = b'{"ok": true}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    port = srv.server_address[1]
    profiles = synthetic(n, n)
    for p in profiles:
        p.url = f"http://127.0.0.1:{port}/item/{p.name.split()[2]}"
        p.method = "GET"
    pm, d = fresh_pm(profiles)
    try:
        win = RunnerWindow(root, pm, _Settings())
        root.update()
        win._delay_var.set("0")

        def run():
            # The engine posts to the Tk loop from its worker thread, so drive a
            # real mainloop (polling with update() is not enough).
            t0 = time.monotonic()

            def poll():
                if not win._running and win._result_queue.empty() and win._runner_result is not None:
                    root.quit()
                elif time.monotonic() - t0 > deadline:
                    root.quit()
                else:
                    root.after(20, poll)

            win._start_run()
            root.after(20, poll)
            root.mainloop()
            if win._runner_result is None:
                raise SystemExit(f"runner did not finish within {deadline}s")
            root.update()

        timed(f"runner real run, {n} requests (localhost)", run)
        assert win._count_done == n == win._count_total, (win._count_done, n)
        assert win._count_passed == n, (win._count_passed, n)
        assert win._prog_label.cget("text") == f"{n} / {n}"
        assert win._passed_label.cget("text") == f"✅ {n}"
        rendered = [r for r in win._result_rows if r is not None]
        assert len(rendered) == min(n, win._MAX_RENDERED_ROWS), len(rendered)
        assert win._runner_result is not None and len(win._runner_result.items) == n
        print(f"  counters ok: {win._count_passed}/{n} passed, {len(rendered)} rows rendered "
              f"(cap {win._MAX_RENDERED_ROWS}), export items {len(win._runner_result.items)}")
        win.destroy()
    finally:
        srv.shutdown()
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

    for n in (50, 616, 2000):
        bench_runner_checklist(root, n)
    bench_runner_run(root, 150)

    root.destroy()
    worst = max(RESULTS, key=lambda x: x[1])
    print(f"\nworst case: {worst[0].strip()} = {worst[1]:.2f}s (limit {args.limit}s)")
    return 1 if worst[1] > args.limit else 0


if __name__ == "__main__":
    sys.exit(main())
