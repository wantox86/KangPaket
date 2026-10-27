"""Runner result detail capture (resolved URL / payload / response body) and counters."""
import json

from app.core.http_client import HttpClient
from app.core.runner_detail import (
    MAX_DETAIL_BYTES, build_detail_sections, format_response_body, truncate_text,
)
from app.core.runner_engine import RunnerEngine
from app.core.runner_state import RunCounters
from app.models.request_model import RequestProfile
from app.models.response_model import ResponseResult
from app.models.runner_model import RunnerConfig


class FakeClient(HttpClient):
    def __init__(self, response=None):
        self.response = response or ResponseResult(
            status_code=200, headers={"Content-Type": "application/json"},
            body='{"ok":true}', size_bytes=11)
        self.sent = []

    def send(self, profile, **kw):
        self.sent.append(profile)
        return self.response


class FakeSettings:
    def get(self, key, default=None):
        return default


def _engine(client, layers):
    eng = RunnerEngine(client, FakeSettings())
    eng._env_layers = layers
    return eng


def _run(eng, profile, csv_row=None):
    return eng._execute_one(profile, 1, RunnerConfig(name="t"), csv_row)


def test_resolved_url_host_path_and_query():
    p = RequestProfile(name="a", url="{{host}}/users/{{id}}", params={"q": "{{term}}"})
    item = _run(_engine(FakeClient(), [{"host": "http://h.test", "id": "7", "term": "a b"}]), p)
    assert item.request_url == "http://h.test/users/7?q=a+b"
    assert "{{" not in item.request_url
    assert item.method == "GET"


def test_csv_overrides_environment_and_globals():
    p = RequestProfile(name="a", url="http://x/{{id}}/{{g}}")
    layers = [{"id": "env"}, {"g": "glob"}]
    item = _run(_engine(FakeClient(), layers), p, {"id": "csv"})
    assert item.request_url == "http://x/csv/glob"


def test_resolved_request_body_raw_and_none():
    p = RequestProfile(name="a", url="http://x", method="POST", body_type="raw",
                       body_content='{"n": "{{name}}"}')
    item = _run(_engine(FakeClient(), [{"name": "bob"}]), p)
    assert item.request_body == '{"n": "bob"}'
    sections = dict(build_detail_sections(item))
    assert sections["Request payload"] == '{"n": "bob"}'
    assert sections["Request URL"].startswith("POST http://x")

    item2 = _run(_engine(FakeClient(), []), RequestProfile(name="b", url="http://x"))
    assert item2.request_body is None
    assert dict(build_detail_sections(item2))["Request payload"] == "(no body)"


def test_form_body_resolved():
    p = RequestProfile(name="a", url="http://x", method="POST",
                       body_type="x-www-form-urlencoded", body_form={"u": "{{u}}"})
    assert _run(_engine(FakeClient(), [{"u": "z"}]), p).request_body == "u=z"


def test_response_body_captured_and_pretty_printed():
    item = _run(_engine(FakeClient(), []), RequestProfile(name="a", url="http://x"))
    assert item.response_body == '{"ok":true}'
    assert dict(build_detail_sections(item))["Response body"] == json.dumps({"ok": True}, indent=2)


def test_error_result_has_url_but_no_response():
    resp = ResponseResult(status_text="ERROR", error="boom")
    item = _run(_engine(FakeClient(resp), []), RequestProfile(name="a", url="http://x/{{v}}"), {"v": "1"})
    assert item.status == "error"
    assert item.request_url == "http://x/1"
    assert item.response_body is None
    assert dict(build_detail_sections(item))["Response body"] == "(no response)"


def test_no_credentials_in_result():
    p = RequestProfile(name="a", url="http://x", auth_type="bearer",
                       auth_data={"token": "SECRET-TOKEN"}, headers={"X-K": "SECRET-HDR"})
    item = _run(_engine(FakeClient(), []), p)
    assert "SECRET" not in repr(item)


def test_truncate_large_body():
    big = "a" * (MAX_DETAIL_BYTES + 5000)
    out = truncate_text(big)
    assert out.startswith("a" * MAX_DETAIL_BYTES)
    assert out.endswith(f"… truncated ({len(big)} bytes total)")
    assert len(out) < MAX_DETAIL_BYTES + 100
    assert truncate_text("small") == "small"
    assert truncate_text(None) is None


def test_truncate_multibyte_is_valid_and_counts_bytes():
    s = "é" * (MAX_DETAIL_BYTES)          # 2 bytes each
    out = truncate_text(s)
    assert f"({MAX_DETAIL_BYTES * 2} bytes total)" in out


def test_engine_truncates_response():
    resp = ResponseResult(status_code=200, body="x" * (MAX_DETAIL_BYTES * 2), size_bytes=MAX_DETAIL_BYTES * 2)
    item = _run(_engine(FakeClient(resp), []), RequestProfile(name="a", url="http://x"))
    assert "truncated" in item.response_body
    assert len(item.response_body) < MAX_DETAIL_BYTES + 100


def test_binary_and_plain_formatting():
    assert format_response_body("\x00\x01", "application/octet-stream", 2).startswith("(binary content")
    assert format_response_body("hello", "text/plain", 5) == "hello"
    assert format_response_body("", "text/plain", 0) == "(empty response)"
    assert format_response_body("{bad", "application/json", 4) == "{bad"


def test_run_counters_reset():
    c = RunCounters()
    c.reset(3)
    for s in ("success", "failed", "error", "skipped"):
        c.add(s)
    assert (c.passed, c.failed, c.errors, c.skipped, c.done, c.total) == (1, 1, 1, 1, 4, 3)
    c.reset(0)
    assert (c.passed, c.failed, c.errors, c.skipped, c.done, c.total) == (0, 0, 0, 0, 0, 0)
