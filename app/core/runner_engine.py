"""
KangPaket — Collection Runner Engine.

Executes RequestProfiles sequentially or in parallel,
evaluates assertions, and emits thread-safe UI callbacks.
"""
from __future__ import annotations

import copy
import json
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable

from app.core.http_client import HttpClient
from app.core.settings_manager import SettingsManager
from app.models.request_model import RequestProfile
from app.models.response_model import ResponseResult
from app.models.runner_model import RunnerConfig, RunItemResult, RunnerResult


# ---------------------------------------------------------------------------
# Assertion helpers
# ---------------------------------------------------------------------------

def _eval_assertions(
    assertions: list[dict],
    result: ResponseResult,
) -> list[dict]:
    """
    Evaluate a list of assertion dicts against a ResponseResult.
    Each assertion dict: {type: str, ...params}
    Returns list of {name, passed, expected, actual} dicts.
    """
    evaluated: list[dict] = []

    for a in assertions:
        atype = a.get("type", "")

        if atype == "status_code_equals":
            expected = a.get("value")
            actual   = result.status_code
            passed   = actual == expected
            evaluated.append({
                "name": f"status_code_equals({expected})",
                "passed": passed,
                "expected": str(expected),
                "actual": str(actual),
            })

        elif atype == "status_code_in":
            expected = a.get("values", [])
            actual   = result.status_code
            passed   = actual in expected
            evaluated.append({
                "name": f"status_code_in({expected})",
                "passed": passed,
                "expected": str(expected),
                "actual": str(actual),
            })

        elif atype == "response_time_less_than":
            limit_ms = a.get("value", 1000)
            actual   = result.elapsed_ms or 0.0
            passed   = actual < limit_ms
            evaluated.append({
                "name": f"response_time_less_than({limit_ms}ms)",
                "passed": passed,
                "expected": f"< {limit_ms}ms",
                "actual": f"{actual:.0f}ms",
            })

        elif atype == "body_contains":
            substring = a.get("value", "")
            passed    = substring in (result.body or "")
            evaluated.append({
                "name": f'body_contains("{substring}")',
                "passed": passed,
                "expected": f'contains "{substring}"',
                "actual": "yes" if passed else "no",
            })

        elif atype == "body_json_path_equals":
            path     = a.get("path", "")
            expected = a.get("value")
            try:
                from jsonpath_ng import parse as jp_parse
                expr    = jp_parse(path)
                body_j  = json.loads(result.body or "{}")
                matches = [m.value for m in expr.find(body_j)]
                actual  = matches[0] if matches else None
                passed  = actual == expected
            except Exception as e:
                actual = f"error: {e}"
                passed = False
            evaluated.append({
                "name": f"body_json_path_equals({path})",
                "passed": passed,
                "expected": str(expected),
                "actual": str(actual),
            })

        elif atype == "header_exists":
            header_name = a.get("value", "").lower()
            headers_lc  = {k.lower() for k in (result.headers or {})}
            passed      = header_name in headers_lc
            evaluated.append({
                "name": f'header_exists("{header_name}")',
                "passed": passed,
                "expected": "exists",
                "actual": "yes" if passed else "no",
            })

        elif atype == "header_equals":
            header_name  = a.get("header", "").lower()
            expected_val = a.get("value", "")
            headers_lc   = {k.lower(): v for k, v in (result.headers or {}).items()}
            actual_val   = headers_lc.get(header_name, "")
            passed       = actual_val == expected_val
            evaluated.append({
                "name": f'header_equals("{header_name}")',
                "passed": passed,
                "expected": expected_val,
                "actual": actual_val,
            })

    return evaluated


# ---------------------------------------------------------------------------
# Runner Engine
# ---------------------------------------------------------------------------

class RunnerEngine:
    def __init__(
        self,
        http_client: HttpClient,
        settings: SettingsManager,
        tk_root=None,
    ) -> None:
        self._client   = http_client
        self._settings = settings
        self._root     = tk_root
        self._stop_flag = threading.Event()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(
        self,
        config: RunnerConfig,
        profiles: list[RequestProfile],
        on_item_done: Callable[[RunItemResult], None],
        on_progress:  Callable[[int, int], None],
        on_finished:  Callable[[RunnerResult], None],
        csv_data: list[dict[str, str]] | None = None,
    ) -> None:
        """Start runner in a background thread.

        csv_data: optional list of variable dicts (one per row).  When provided
        the runner uses len(csv_data) as the iteration count and substitutes
        {{VariableName}} placeholders in every profile field for each row.
        """
        self._stop_flag.clear()
        thread = threading.Thread(
            target=self._run_thread,
            args=(config, profiles, on_item_done, on_progress, on_finished, csv_data),
            daemon=True,
        )
        thread.start()

    def stop(self) -> None:
        """Signal the runner to stop after the current request."""
        self._stop_flag.set()

    # ------------------------------------------------------------------
    # Internal — thread entry point
    # ------------------------------------------------------------------

    def _run_thread(
        self,
        config: RunnerConfig,
        profiles: list[RequestProfile],
        on_item_done: Callable,
        on_progress: Callable,
        on_finished: Callable,
        csv_data: list[dict[str, str]] | None = None,
    ) -> None:
        start_wall = time.monotonic()

        # Determine iteration count: CSV rows override config.iteration_count
        iter_count = len(csv_data) if csv_data else config.iteration_count

        # Build ordered list of (profile, iteration, variables) work items
        work_items: list[tuple[RequestProfile, int, dict[str, str] | None]] = []
        for profile in profiles:
            for i in range(iter_count):
                iteration = i + 1
                variables = csv_data[i] if csv_data else None
                work_items.append((profile, iteration, variables))

        total    = len(work_items)
        results: list[RunItemResult] = []

        if config.run_mode == "parallel":
            results = self._run_parallel(
                config, work_items, total, on_item_done, on_progress
            )
        else:
            results = self._run_sequential(
                config, work_items, total, on_item_done, on_progress
            )

        total_elapsed = (time.monotonic() - start_wall) * 1000

        runner_result = RunnerResult(
            config=config,
            items=results,
            total=total,
            passed=sum(1 for r in results if r.status == "success"),
            failed=sum(1 for r in results if r.status == "failed"),
            errors=sum(1 for r in results if r.status == "error"),
            skipped=sum(1 for r in results if r.status == "skipped"),
            total_elapsed_ms=total_elapsed,
        )

        self._ui_call(on_finished, runner_result)

    # ------------------------------------------------------------------
    # Sequential execution
    # ------------------------------------------------------------------

    def _run_sequential(
        self,
        config: RunnerConfig,
        work_items: list[tuple[RequestProfile, int, dict[str, str] | None]],
        total: int,
        on_item_done: Callable,
        on_progress: Callable,
    ) -> list[RunItemResult]:
        results: list[RunItemResult] = []
        done = 0
        should_stop = False

        for profile, iteration, variables in work_items:
            if self._stop_flag.is_set() or should_stop:
                item = RunItemResult(
                    profile_id=profile.id,
                    profile_name=profile.name,
                    iteration=iteration,
                    status="skipped",
                )
                results.append(item)
                self._ui_call(on_item_done, item)
                done += 1
                self._ui_call(on_progress, done, total)
                continue

            item = self._execute_one(profile, iteration, config, variables)
            results.append(item)
            self._ui_call(on_item_done, item)
            done += 1
            self._ui_call(on_progress, done, total)

            if config.stop_on_failure and item.status in ("failed", "error"):
                should_stop = True

            if config.delay_between_ms > 0 and not self._stop_flag.is_set():
                time.sleep(config.delay_between_ms / 1000)

        return results

    # ------------------------------------------------------------------
    # Parallel execution
    # ------------------------------------------------------------------

    def _run_parallel(
        self,
        config: RunnerConfig,
        work_items: list[tuple[RequestProfile, int, dict[str, str] | None]],
        total: int,
        on_item_done: Callable,
        on_progress: Callable,
    ) -> list[RunItemResult]:
        results_lock = threading.Lock()
        results: list[RunItemResult] = []
        done_count   = [0]
        abort        = threading.Event()

        max_workers = min(len(work_items), 5)

        def run_one(
            profile: RequestProfile,
            iteration: int,
            variables: dict[str, str] | None,
        ) -> RunItemResult:
            if self._stop_flag.is_set() or abort.is_set():
                return RunItemResult(
                    profile_id=profile.id,
                    profile_name=profile.name,
                    iteration=iteration,
                    status="skipped",
                )
            return self._execute_one(profile, iteration, config, variables)

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_map = {
                executor.submit(run_one, profile, iteration, variables): (profile, iteration)
                for profile, iteration, variables in work_items
            }

            for future in as_completed(future_map):
                item = future.result()

                with results_lock:
                    results.append(item)
                    done_count[0] += 1
                    done = done_count[0]

                self._ui_call(on_item_done, item)
                self._ui_call(on_progress, done, total)

                if config.stop_on_failure and item.status in ("failed", "error"):
                    abort.set()

        return results

    # ------------------------------------------------------------------
    # Single request execution
    # ------------------------------------------------------------------

    def _execute_one(
        self,
        profile: RequestProfile,
        iteration: int,
        config: RunnerConfig,
        variables: dict[str, str] | None = None,
    ) -> RunItemResult:
        # Apply CSV variable substitution to a copy of the profile
        if variables:
            profile = self._apply_vars_to_profile(profile, variables)

        timeout       = self._settings.get("default_timeout", 30.0)
        proxy_enabled = self._settings.get("proxy_enabled", False)
        proxy_http    = self._settings.get("proxy_http", "")
        proxy_https   = self._settings.get("proxy_https", "")

        response = self._client.send(
            profile,
            default_timeout=timeout,
            proxy_enabled=proxy_enabled,
            proxy_http=proxy_http,
            proxy_https=proxy_https,
        )

        # Evaluate assertions (stored on profile as metadata — Sprint 7 uses
        # assertions passed via RunnerConfig; here we support profile-level ones)
        assertions_cfg = getattr(profile, "_assertions", [])
        assertion_results = _eval_assertions(assertions_cfg, response)

        has_assertion_fail = any(not a["passed"] for a in assertion_results)

        if response.is_error:
            status = "error"
        elif has_assertion_fail:
            status = "failed"
        else:
            status = "success"

        return RunItemResult(
            profile_id=profile.id,
            profile_name=profile.name,
            iteration=iteration,
            status=status,
            status_code=response.status_code if not response.is_error else None,
            elapsed_ms=response.elapsed_ms if not response.is_error else None,
            size_bytes=response.size_bytes if not response.is_error else None,
            error=response.error,
            assertion_results=assertion_results,
        )

    # ------------------------------------------------------------------
    # Variable substitution
    # ------------------------------------------------------------------

    @staticmethod
    def _substitute_vars(text: str, variables: dict[str, str]) -> str:
        """Replace {{VarName}} placeholders with values from *variables*.
        Unrecognised placeholders are left as-is."""
        def _replace(match: re.Match) -> str:
            return variables.get(match.group(1), match.group(0))
        return re.sub(r"\{\{([^}]+)\}\}", _replace, text)

    def _apply_vars_to_profile(
        self, profile: RequestProfile, variables: dict[str, str]
    ) -> RequestProfile:
        """Return a shallow-copied profile with all {{var}} placeholders resolved."""
        sub = self._substitute_vars
        p = copy.copy(profile)
        p.url          = sub(p.url, variables)
        p.headers      = {k: sub(v, variables) for k, v in p.headers.items()}
        p.params       = {k: sub(v, variables) for k, v in p.params.items()}
        p.body_content = sub(p.body_content, variables)
        p.body_form    = {k: sub(v, variables) for k, v in p.body_form.items()}
        p.auth_data    = {k: sub(str(v), variables) for k, v in p.auth_data.items()}
        return p

    # ------------------------------------------------------------------
    # Thread-safe UI callback
    # ------------------------------------------------------------------

    def _ui_call(self, fn: Callable, *args) -> None:
        """Schedule callback on the tkinter main thread if root is available."""
        if self._root is not None:
            self._root.after(0, fn, *args)
        else:
            fn(*args)
