"""
KangPaket — Code snippet generators (strategy pattern).

One ``Generator`` subclass per target language; ``generate(language, profile)``
dispatches through the ``GENERATORS`` registry. Generators are pure functions of
a ``RequestProfile``, so they are unit-testable with no GUI and no network.

To add a language: subclass ``Generator``, set a unique ``key``/``label``, and
register it in ``GENERATORS``. Nothing else changes — the UI reads ``LANGUAGES``.

ponytail: basic auth is emitted as an ``Authorization: Basic …`` header in every
language (uniform + correct) rather than per-language idioms (``-u``, ``auth=``).
    add when: idiomatic output matters more than uniform output.
ponytail: no syntax highlighting — tkinter's Text widget has no native
highlighter and a regex tokenizer per language is a separate feature.
    add when: a user asks for coloured code in the viewer.
ponytail: Go/PHP/Java are minimal, compile-shaped snippets (no auth idiom, no
package/import scaffolding beyond what is needed).
    add when: a user wants copy-paste-runnable full programs.
"""
from __future__ import annotations

import base64
import json
import urllib.parse

from app.models.request_model import RequestProfile


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _quote(value: str) -> str:
    """Quote ``value`` for POSIX shell using single quotes (the ``'\\''`` idiom)."""
    return "'" + value.replace("'", "'\\''") + "'"


def _json(value: str) -> str:
    """JSON-stringify a Python string (valid double-quoted literal in JS/Go/PHP/Java)."""
    return json.dumps(value, ensure_ascii=False)


def _url(profile: RequestProfile) -> str:
    url = profile.url.strip()
    if profile.params:
        url += ("&" if "?" in url else "?") + urllib.parse.urlencode(profile.params)
    return url


def _headers(profile: RequestProfile) -> dict[str, str]:
    headers = dict(profile.headers)
    if profile.auth_type == "bearer":
        headers["Authorization"] = "Bearer " + profile.auth_data.get("token", "")
    elif profile.auth_type == "basic":
        u = profile.auth_data.get("username", "")
        p = profile.auth_data.get("password", "")
        cred = base64.b64encode(f"{u}:{p}".encode("utf-8")).decode("ascii")
        headers["Authorization"] = "Basic " + cred
    elif profile.auth_type == "api-key" and profile.auth_data.get("in", "header") == "header":
        headers[profile.auth_data.get("key", "X-API-Key")] = profile.auth_data.get("value", "")
    return headers


def _form_pairs(profile: RequestProfile) -> list[tuple[str, str]]:
    return list(profile.body_form.items())


def _urlencoded(profile: RequestProfile) -> str:
    return urllib.parse.urlencode(profile.body_form)


# ---------------------------------------------------------------------------
# Generators
# ---------------------------------------------------------------------------

class Generator:
    key = "base"
    label = "Base"

    def generate(self, profile: RequestProfile) -> str:
        raise NotImplementedError


class CurlGenerator(Generator):
    key = "curl"
    label = "cURL"

    def generate(self, profile: RequestProfile) -> str:
        parts = [f"curl --request {profile.method.upper()}"]
        for k, v in _headers(profile).items():
            parts.append(f"--header {_quote(f'{k}: {v}')}")
        t = profile.body_type
        if t == "raw" and profile.body_content:
            parts.append(f"--data-raw {_quote(profile.body_content)}")
        elif t == "form-data":
            parts += [f"--form {_quote(f'{k}={v}')}" for k, v in _form_pairs(profile)]
        elif t == "x-www-form-urlencoded":
            parts += [f"--data-urlencode {_quote(f'{k}={v}')}" for k, v in _form_pairs(profile)]
        parts.append(_quote(_url(profile)))
        return " \\\n".join(parts)


class FetchGenerator(Generator):
    key = "javascript-fetch"
    label = "JavaScript (fetch)"

    def generate(self, profile: RequestProfile) -> str:
        url = _url(profile)
        method = profile.method.upper()
        headers = _headers(profile)
        out: list[str] = []

        if profile.body_type == "form-data" and profile.body_form:
            out.append("const form = new FormData();")
            for k, v in _form_pairs(profile):
                out.append(f"form.append({_json(k)}, {_json(v)});")
            opts: list[str] = []
            if method != "GET":
                opts.append(f"  method: {_json(method)}")
            if headers:
                opts.append(_headers_block(headers))
            opts.append("  body: form")
            out.append(f"fetch({_json(url)}, {{\n" + ",\n".join(opts) + "\n});")
            return "\n".join(out)

        opts = []
        if method != "GET":
            opts.append(f"  method: {_json(method)}")
        if headers:
            opts.append(_headers_block(headers))
        body = self._inline_body(profile)
        if body is not None:
            opts.append(f"  body: {body}")
        if opts:
            out.append(f"fetch({_json(url)}, {{\n" + ",\n".join(opts) + "\n});")
        else:
            out.append(f"fetch({_json(url)});")
        return "\n".join(out)

    @staticmethod
    def _inline_body(profile: RequestProfile) -> str | None:
        if profile.body_type == "raw" and profile.body_content:
            return _json(profile.body_content)
        if profile.body_type == "x-www-form-urlencoded" and profile.body_form:
            return _json(_urlencoded(profile))
        return None


class AxiosGenerator(Generator):
    key = "javascript-axios"
    label = "JavaScript (axios)"

    def generate(self, profile: RequestProfile) -> str:
        url = _url(profile)
        headers = _headers(profile)
        pre: list[str] = []
        opts = [f"  method: {_json(profile.method.lower())}", f"  url: {_json(url)}"]
        if headers:
            opts.append(_headers_block(headers))
        if profile.body_type == "form-data" and profile.body_form:
            pre.append("const form = new FormData();")
            pre += [f"form.append({_json(k)}, {_json(v)});" for k, v in _form_pairs(profile)]
            opts.append("  data: form")
        elif profile.body_type == "raw" and profile.body_content:
            opts.append(f"  data: {_json(profile.body_content)}")
        elif profile.body_type == "x-www-form-urlencoded" and profile.body_form:
            opts.append(f"  data: {_json(_urlencoded(profile))}")
        body = "\n".join(opts)
        pre.append("axios({\n" + body + "\n});")
        return "\n".join(pre)


class PythonRequestsGenerator(Generator):
    key = "python-requests"
    label = "Python (requests)"

    def generate(self, profile: RequestProfile) -> str:
        url = _url(profile)
        headers = _headers(profile)
        kwargs: list[str] = []
        if headers:
            kwargs.append(f"headers={headers!r}")
        if profile.body_type == "raw" and profile.body_content:
            kwargs.append(f"data={profile.body_content!r}")
        elif profile.body_type == "x-www-form-urlencoded" and profile.body_form:
            kwargs.append(f"data={dict(profile.body_form)!r}")
        elif profile.body_type == "form-data" and profile.body_form:
            files = {k: (None, v) for k, v in _form_pairs(profile)}
            kwargs.append(f"files={files!r}")

        call = f"response = requests.{profile.method.lower()}({url!r}"
        if kwargs:
            call += ", " + ", ".join(kwargs)
        call += ")"
        return "import requests\n\n" + call


class GoGenerator(Generator):
    key = "go"
    label = "Go (net/http)"

    def generate(self, profile: RequestProfile) -> str:
        url = _url(profile)
        method = profile.method.upper()
        headers = _headers(profile)
        lines = ["package main", "", "import (", '\t"net/http"']
        has_body = (profile.body_type == "raw" and profile.body_content) or (
            profile.body_type in ("x-www-form-urlencoded", "form-data") and profile.body_form
        )
        if has_body:
            lines.append('\t"strings"')
        lines += [")", "", "func main() {"]
        if profile.body_type == "raw" and profile.body_content:
            data = profile.body_content
        elif profile.body_type in ("x-www-form-urlencoded", "form-data") and profile.body_form:
            data = _urlencoded(profile)
        else:
            data = None
        if data is not None:
            lines.append(f"\tbody := strings.NewReader({_json(data)})")
            body_arg = "body"
        else:
            body_arg = "nil"
        lines.append(f"\treq, err := http.NewRequest({_json(method)}, {_json(url)}, {body_arg})")
        lines += ["\tif err != nil {", "\t\tpanic(err)", "\t}"]
        for k, v in headers.items():
            lines.append(f"\treq.Header.Set({_json(k)}, {_json(v)})")
        lines += [
            "\tresp, err := http.DefaultClient.Do(req)",
            "\tif err != nil {",
            "\t\tpanic(err)",
            "\t}",
            "\tdefer resp.Body.Close()",
            "}",
        ]
        return "\n".join(lines)


class PhpCurlGenerator(Generator):
    key = "php-curl"
    label = "PHP (cURL)"

    def generate(self, profile: RequestProfile) -> str:
        url = _url(profile)
        method = profile.method.upper()
        headers = _headers(profile)
        lines = [
            "$ch = curl_init();",
            f"curl_setopt($ch, CURLOPT_URL, {_json(url)});",
            "curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);",
            f"curl_setopt($ch, CURLOPT_CUSTOMREQUEST, {_json(method)});",
        ]
        if headers:
            inner = ",\n".join(f"\t{_json(f'{k}: {v}')}" for k, v in headers.items())
            lines.append("curl_setopt($ch, CURLOPT_HTTPHEADER, array(")
            lines.append(inner + "\n));")
        if profile.body_type == "raw" and profile.body_content:
            lines.append(f"curl_setopt($ch, CURLOPT_POSTFIELDS, {_json(profile.body_content)});")
        elif profile.body_type in ("x-www-form-urlencoded", "form-data") and profile.body_form:
            lines.append(f"curl_setopt($ch, CURLOPT_POSTFIELDS, {_json(_urlencoded(profile))});")
        lines += ["$response = curl_exec($ch);", "curl_close($ch);"]
        return "\n".join(lines)


class JavaOkHttpGenerator(Generator):
    key = "java-okhttp"
    label = "Java (OkHttp)"

    def generate(self, profile: RequestProfile) -> str:
        url = _url(profile)
        method = profile.method.upper()
        headers = _headers(profile)
        ct = headers.get("Content-Type", "application/json")
        lines = ["OkHttpClient client = new OkHttpClient();", ""]
        if profile.body_type == "raw" and profile.body_content:
            method_arg = f'"{method}", RequestBody.create({_json(profile.body_content)}, MediaType.parse({_json(ct)}))'
        elif profile.body_type in ("x-www-form-urlencoded", "form-data") and profile.body_form:
            ct = headers.get("Content-Type", "application/x-www-form-urlencoded")
            method_arg = f'"{method}", RequestBody.create({_json(_urlencoded(profile))}, MediaType.parse({_json(ct)}))'
        else:
            method_arg = f'"{method}", null'
        lines.append("Request request = new Request.Builder()")
        lines.append(f"    .url({_json(url)})")
        for k, v in headers.items():
            lines.append(f"    .addHeader({_json(k)}, {_json(v)})")
        lines.append(f"    .method({method_arg})")
        lines.append("    .build();")
        lines += ["", "Response response = client.newCall(request).execute();"]
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

def _headers_block(headers: dict[str, str]) -> str:
    inner = ",\n".join(f"    {_json(k)}: {_json(v)}" for k, v in headers.items())
    return f"  headers: {{\n{inner}\n  }}"


GENERATORS: dict[str, type[Generator]] = {
    CurlGenerator.key: CurlGenerator,
    FetchGenerator.key: FetchGenerator,
    AxiosGenerator.key: AxiosGenerator,
    PythonRequestsGenerator.key: PythonRequestsGenerator,
    GoGenerator.key: GoGenerator,
    PhpCurlGenerator.key: PhpCurlGenerator,
    JavaOkHttpGenerator.key: JavaOkHttpGenerator,
}

LANGUAGES: list[str] = list(GENERATORS)
LANGUAGE_LABELS: dict[str, str] = {g.key: g.label for g in GENERATORS.values()}


def generate(language: str, profile: RequestProfile) -> str:
    cls = GENERATORS.get(language)
    if cls is None:
        return ""
    return cls().generate(profile)
