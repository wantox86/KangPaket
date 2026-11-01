"""Unit tests for app/core/codegen.py (pure generators, no GUI, no network)."""
import pytest

from app.core.codegen import generate, LANGUAGES
from app.models.request_model import RequestProfile


def p(**kw):
    defaults = dict(name="t", url="https://api.example.com/users")
    defaults.update(kw)
    return RequestProfile(**defaults)


def test_all_languages_registered():
    assert LANGUAGES == [
        "curl", "javascript-fetch", "javascript-axios", "python-requests",
        "go", "php-curl", "java-okhttp",
    ]


# ---------------------------------------------------------------------------
# cURL
# ---------------------------------------------------------------------------

def test_curl_simple_get():
    out = generate("curl", p())
    assert "curl --request GET" in out
    assert "https://api.example.com/users" in out


def test_curl_headers_and_query():
    out = generate("curl", p(headers={"Accept": "application/json"}, params={"q": "hello world"}))
    assert "--header 'Accept: application/json'" in out
    assert "hello+world" in out


def test_curl_quote_escaping():
    out = generate("curl", p(headers={"X-Token": "it's 'quoted'"}))
    # POSIX single-quote idiom: it'\''s '\''quoted'\''
    assert "--header 'X-Token: it'\\''s '\\''quoted'\\''" in out


def test_curl_bearer_and_body():
    out = generate(
        "curl",
        p(method="POST", auth_type="bearer", auth_data={"token": "secret"},
          body_type="raw", body_content='{"a": 1}'),
    )
    assert "--header 'Authorization: Bearer secret'" in out
    assert "--data-raw '{\"a\": 1}'" in out


def test_curl_form_data():
    out = generate("curl", p(method="POST", body_type="form-data", body_form={"name": "a b"}))
    assert "--form 'name=a b'" in out


def test_curl_urlencoded():
    out = generate("curl", p(method="POST", body_type="x-www-form-urlencoded", body_form={"a": "1"}))
    assert "--data-urlencode 'a=1'" in out


# ---------------------------------------------------------------------------
# JavaScript fetch
# ---------------------------------------------------------------------------

def test_fetch_get_with_headers():
    out = generate("fetch" if False else "javascript-fetch", p(headers={"Accept": "application/json"}))
    assert "fetch(" in out and "headers: {" in out


def test_fetch_json_body():
    out = generate("javascript-fetch", p(method="POST", body_type="raw", body_content='{"a":1}'))
    assert "method: \"POST\"" in out
    assert "body: \"{\\\"a\\\":1}\"" in out


def test_fetch_formdata():
    out = generate("javascript-fetch", p(method="POST", body_type="form-data", body_form={"a": "1"}))
    assert "new FormData()" in out and "form.append(\"a\", \"1\")" in out


# ---------------------------------------------------------------------------
# Python requests
# ---------------------------------------------------------------------------

def test_python_requests():
    out = generate("python-requests", p(method="POST", headers={"Accept": "application/json"},
                                        body_type="raw", body_content='{"a":1}'))
    assert "import requests" in out
    assert "requests.post(" in out
    assert "headers={'Accept': 'application/json'}" in out


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

def test_empty_url_still_generates():
    out = generate("curl", p(url=""))
    assert "curl --request GET" in out


def test_empty_body_no_data_flag():
    out = generate("curl", p(method="POST", body_type="raw", body_content=""))
    assert "--data-raw" not in out


def test_non_ascii_kept():
    out = generate("curl", p(url="https://api.example.com/café"))
    assert "café" in out


def test_unknown_language_returns_empty():
    assert generate("nope", p()) == ""


def test_go_php_java_shape():
    assert "http.NewRequest" in generate("go", p())
    assert "curl_init()" in generate("php-curl", p())
    assert "new Request.Builder()" in generate("java-okhttp", p())
