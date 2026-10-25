"""
KangPaket — cURL command parser (pure logic, no GUI, nothing is executed).

parse_curl(text) -> CurlImportResult(profile, warnings)
Raises CurlParseError with a human-readable message for unusable input.

Supports what "Copy as cURL (bash)" from Chrome/Firefox/Postman and hand-written
commands normally contain: URL / --url, -X, -H, -d family, --json, -G, -u, -b,
-F, -A, -e, -I, -k, plus ignored flags (--compressed, -L, -s, -v, ...), `\\`+newline
continuations, '...', "...", $'...' quoting and clustered short flags (-sSL).
Files (-d @file, -F x=@file) are never read; they produce a warning instead.
"""
from __future__ import annotations

import re
import urllib.parse
from dataclasses import dataclass, field

from app.config import HTTP_METHODS
from app.models.request_model import RequestProfile


class CurlParseError(ValueError):
    """Input is not a parseable cURL command."""


@dataclass
class CurlImportResult:
    profile: RequestProfile
    warnings: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------
# Tokenizer (POSIX-ish shell words, plus $'...' ANSI-C quoting)
# --------------------------------------------------------------------------

_ANSI_SIMPLE = {
    "n": "\n", "t": "\t", "r": "\r", "a": "\a", "b": "\b", "f": "\f",
    "v": "\v", "e": "\x1b", "E": "\x1b", "\\": "\\", "'": "'", '"': '"', "?": "?",
}


def _read_ansi_c(s: str, i: int) -> tuple[str, int]:
    """s[i] is the first char after $' . Returns (decoded, index after closing quote)."""
    out: list[str] = []
    n = len(s)
    while i < n:
        c = s[i]
        if c == "'":
            return "".join(out), i + 1
        if c != "\\":
            out.append(c)
            i += 1
            continue
        i += 1
        if i >= n:
            break
        c = s[i]
        if c in _ANSI_SIMPLE:
            out.append(_ANSI_SIMPLE[c])
            i += 1
        elif c == "x":
            m = re.match(r"[0-9a-fA-F]{1,2}", s[i + 1:])
            if m:
                out.append(chr(int(m.group(), 16)))
                i += 1 + len(m.group())
            else:
                out.append("\\x")
                i += 1
        elif c in "uU":
            width = 4 if c == "u" else 8
            m = re.match(r"[0-9a-fA-F]{1,%d}" % width, s[i + 1:])
            if m:
                try:
                    out.append(chr(int(m.group(), 16)))
                except (ValueError, OverflowError):
                    raise CurlParseError("Invalid unicode escape in $'...' string.")
                i += 1 + len(m.group())
            else:
                out.append("\\" + c)
                i += 1
        elif c in "01234567":
            m = re.match(r"[0-7]{1,3}", s[i:])
            out.append(chr(int(m.group(), 8) & 0xFF))
            i += len(m.group())
        else:
            out.append("\\" + c)
            i += 1
    raise CurlParseError("Unterminated $'...' quote.")


def tokenize(text: str) -> list[str]:
    """Split a shell command line into words. Raises CurlParseError on unbalanced quotes."""
    # Line continuation: backslash + newline (LF or CRLF) -> nothing.
    # Only outside single quotes in real shells, but pasted commands never rely on that.
    text = re.sub(r"\\\r?\n", "", text)
    tokens: list[str] = []
    cur: list[str] = []
    in_token = False
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c in " \t\r\n":
            if in_token:
                tokens.append("".join(cur))
                cur, in_token = [], False
            i += 1
        elif c == "#" and not in_token:
            while i < n and text[i] != "\n":      # comment to end of line
                i += 1
        elif c == "'":
            end = text.find("'", i + 1)
            if end == -1:
                raise CurlParseError("Unterminated single quote (').")
            cur.append(text[i + 1:end])
            in_token = True
            i = end + 1
        elif c == "$" and text.startswith("$'", i):
            s, i = _read_ansi_c(text, i + 2)
            cur.append(s)
            in_token = True
        elif c == '"':
            i += 1
            in_token = True
            while True:
                if i >= n:
                    raise CurlParseError('Unterminated double quote (").')
                d = text[i]
                if d == '"':
                    i += 1
                    break
                if d == "\\" and i + 1 < n and text[i + 1] in '"\\$`':
                    cur.append(text[i + 1])
                    i += 2
                else:
                    cur.append(d)
                    i += 1
        elif c == "\\":
            if i + 1 < n:
                cur.append(text[i + 1])
                i += 2
            else:
                i += 1
            in_token = True
        else:
            cur.append(c)
            in_token = True
            i += 1
    if in_token:
        tokens.append("".join(cur))
    return tokens


# --------------------------------------------------------------------------
# Option tables
# --------------------------------------------------------------------------

# canonical name -> takes an argument?
_SHORT_WITH_ARG = {
    "X": "request", "H": "header", "d": "data", "u": "user", "b": "cookie",
    "F": "form", "A": "user-agent", "e": "referer", "m": "max-time",
    "o": "output", "x": "proxy", "T": "upload-file", "w": "write-out",
    "c": "cookie-jar", "E": "cert", "K": "config", "r": "range", "C": "continue-at",
    "D": "dump-header", "y": "speed-time", "Y": "speed-limit", "z": "time-cond",
    "U": "proxy-user", "t": "telnet-option", "Q": "quote", "P": "ftp-port",
}
_SHORT_FLAGS = {
    "G": "get", "I": "head", "k": "insecure", "L": "location", "s": "silent",
    "S": "show-error", "v": "verbose", "f": "fail", "i": "include", "O": "remote-name",
    "j": "junk-session-cookies", "g": "globoff", "N": "no-buffer", "n": "netrc",
    "q": "disable", "Z": "parallel", "0": "http1.0", "1": "tlsv1", "2": "sslv2",
    "3": "sslv3", "4": "ipv4", "6": "ipv6", "B": "use-ascii", "a": "append",
    "l": "list-only", "p": "proxytunnel", "R": "remote-time", "J": "remote-header-name",
}
_LONG_WITH_ARG = {
    "request", "header", "data", "data-raw", "data-binary", "data-ascii",
    "data-urlencode", "json", "user", "cookie", "form", "url", "user-agent",
    "referer", "max-time", "connect-timeout", "output", "proxy", "upload-file",
    "write-out", "cookie-jar", "cert", "key", "cacert", "capath", "config",
    "range", "retry", "retry-delay", "retry-max-time", "limit-rate", "resolve",
    "connect-to", "interface", "dump-header", "proxy-user", "oauth2-bearer",
    "max-redirs", "request-target", "form-string", "cert-type",
    "variable", "expand-data", "aws-sigv4",
    "unix-socket", "dns-servers", "doh-url", "ciphers", "proto", "proto-redir",
}
_LONG_FLAGS = {
    "get", "head", "insecure", "location", "silent", "show-error", "verbose",
    "fail", "include", "compressed", "compressed-ssh", "globoff", "no-buffer",
    "http1.0", "http1.1", "http2", "http2-prior-knowledge", "http3", "ipv4",
    "ipv6", "netrc", "remote-name", "location-trusted", "tr-encoding",
    "no-keepalive", "tcp-nodelay", "path-as-is", "raw", "styled-output",
    "fail-with-body", "progress-bar", "disable", "tlsv1", "tlsv1.0", "tlsv1.1",
    "tlsv1.2", "tlsv1.3", "parallel", "no-progress-meter", "anyauth", "basic",
    "digest", "ntlm", "negotiate", "proxy-insecure", "ssl", "ssl-reqd",
    "suppress-connect-headers", "junk-session-cookies", "remote-time",
    "remote-header-name", "create-dirs", "xattr",
}
_ERR_NO_URL = "No URL found in the cURL command."


def _urlencode_data(item: str, warnings: list[str]) -> str:
    """Implements --data-urlencode content forms: content, =content, name=content, @file, name@file."""
    if "=" in item:
        name, _, content = item.partition("=")
        enc = urllib.parse.quote_plus(content, safe="")
        return f"{name}={enc}" if name else enc
    if "@" in item:
        warnings.append("--data-urlencode with @file is not supported (files are never read); skipped.")
        return ""
    return urllib.parse.quote_plus(item, safe="")


def _looks_like_form(data: str) -> bool:
    if not data or data[0] in "{[<\"'" or "\n" in data.strip():
        return False
    return all("=" in part for part in data.split("&"))


def _parse_form_pairs(data: str) -> list[tuple[str, str]]:
    return [
        (urllib.parse.unquote_plus(k), urllib.parse.unquote_plus(v))
        for k, _, v in (p.partition("=") for p in data.split("&") if p != "")
    ]


def parse_curl(text: str) -> CurlImportResult:
    """Parse a cURL command string into a RequestProfile (never executes anything)."""
    if text is None or not text.strip():
        raise CurlParseError("Nothing to import: the cURL command is empty.")

    tokens = tokenize(text.strip())
    if not tokens:
        raise CurlParseError("Nothing to import: the cURL command is empty.")

    # Tolerate pasted prompts / env prefixes: "$ curl ...", "sudo curl ..."
    while tokens and tokens[0] in ("$", ">", "sudo"):
        tokens.pop(0)
    if not tokens or tokens[0].lower() not in ("curl", "curl.exe"):
        raise CurlParseError("This does not look like a cURL command (it must start with 'curl').")
    tokens = tokens[1:]

    warnings: list[str] = []
    urls: list[str] = []
    method: str | None = None
    headers: dict[str, str] = {}
    data_parts: list[str] = []
    form_fields: list[tuple[str, str]] = []
    user: str | None = None
    cookies: list[str] = []
    get_mode = False
    head_mode = False
    insecure = False
    json_mode = False
    ignored: list[str] = []

    def add_header(raw: str) -> None:
        if ":" in raw:
            name, _, value = raw.partition(":")
            name, value = name.strip(), value.strip()
            if not name:
                warnings.append(f"Skipped malformed header: {raw!r}")
            else:
                if name.lower() in {k.lower() for k in headers} and name.lower() != "cookie":
                    for existing in [k for k in headers if k.lower() == name.lower()]:
                        del headers[existing]
                    warnings.append(f"Header '{name}' given more than once; last value kept.")
                if name.lower() == "cookie":
                    cookies.append(value)
                else:
                    headers[name] = value
        elif raw.endswith(";"):
            headers[raw[:-1].strip()] = ""
        else:
            warnings.append(f"Skipped malformed header (no ':'): {raw!r}")

    def apply(name: str, value: str | None) -> None:
        nonlocal method, user, get_mode, head_mode, insecure, json_mode
        if name == "request":
            method = value.strip().upper()
        elif name == "header":
            add_header(value)
        elif name in ("data", "data-ascii", "data-raw", "data-binary"):
            if name != "data-raw" and value.startswith("@"):
                warnings.append(f"--{name} {value}: reading files is not supported; data skipped.")
            else:
                data_parts.append(value)
        elif name == "data-urlencode":
            enc = _urlencode_data(value, warnings)
            if enc:
                data_parts.append(enc)
        elif name == "json":
            if value.startswith("@"):
                warnings.append("--json @file is not supported; data skipped.")
            else:
                data_parts.append(value)
                json_mode = True
        elif name == "user":
            user = value
        elif name == "cookie":
            if "=" in value:
                cookies.append(value)
            else:
                warnings.append("-b/--cookie with a file name is not supported; skipped.")
        elif name in ("form", "form-string"):
            k, sep, v = value.partition("=")
            if not sep or not k:
                warnings.append(f"Skipped malformed -F value: {value!r}")
            elif name == "form" and v.startswith(("@", "<")):
                warnings.append(f"-F {k}=...: file uploads are not supported; kept the text {v!r} as value.")
                form_fields.append((k, v))
            else:
                if name == "form":
                    v = re.sub(r";(type|filename|headers)=[^;]*$", "", v)
                form_fields.append((k, v))
        elif name == "url":
            urls.append(value)
        elif name == "user-agent":
            headers["User-Agent"] = value
        elif name == "referer":
            headers["Referer"] = value
        elif name == "get":
            get_mode = True
        elif name == "head":
            head_mode = True
        elif name == "insecure":
            insecure = True
        else:
            ignored.append(("-" if len(name) == 1 else "--") + name)

    i = 0
    only_args = False
    while i < len(tokens):
        tok = tokens[i]
        i += 1
        if only_args or not tok.startswith("-") or tok == "-":
            urls.append(tok)
            continue
        if tok == "--":
            only_args = True
            continue

        if tok.startswith("--"):
            name, eq, inline = tok[2:].partition("=")
            if name.startswith("no-") and name not in _LONG_FLAGS and name[3:] in (_LONG_FLAGS | _LONG_WITH_ARG):
                ignored.append(tok)
                continue
            if name in _LONG_WITH_ARG:
                if eq:
                    val = inline
                elif i < len(tokens):
                    val = tokens[i]
                    i += 1
                else:
                    raise CurlParseError(f"Option --{name} needs a value but the command ends there.")
                apply(name, val)
            elif name in _LONG_FLAGS:
                apply(name, None)
            else:
                warnings.append(f"Unknown option {tok!r} ignored (if it takes a value, the value may be misread as the URL).")
            continue

        # short option cluster, e.g. -sSL, -XPOST, -H'A: b'
        j = 1
        while j < len(tok):
            ch = tok[j]
            if ch in _SHORT_WITH_ARG:
                rest = tok[j + 1:]
                if rest:
                    val = rest
                elif i < len(tokens):
                    val = tokens[i]
                    i += 1
                else:
                    raise CurlParseError(f"Option -{ch} needs a value but the command ends there.")
                apply(_SHORT_WITH_ARG[ch], val)
                break
            if ch in _SHORT_FLAGS:
                apply(_SHORT_FLAGS[ch], None)
            else:
                warnings.append(f"Unknown option '-{ch}' ignored.")
            j += 1

    if ignored:
        uniq = ", ".join(dict.fromkeys(ignored))
        warnings.append(f"Ignored options (no effect on the request): {uniq}")

    if not urls:
        raise CurlParseError(_ERR_NO_URL)
    if len(urls) > 1:
        warnings.append(f"Multiple URLs found; only the first is imported ({len(urls) - 1} ignored).")
    url = urls[0].strip()
    if not url:
        raise CurlParseError(_ERR_NO_URL)
    if not re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", url):
        if re.match(r"^[\w.\-\[\]:{}@%]+(/|\?|:\d|$)", url) and " " not in url:
            url = "http://" + url        # curl itself assumes http:// here
        else:
            raise CurlParseError(f"Could not recognise a URL: {urls[0]!r}")
    scheme = url.split("://", 1)[0].lower()
    if scheme not in ("http", "https"):
        raise CurlParseError(f"Unsupported URL scheme '{scheme}://' (only http and https can be imported).")

    # ---- Cookies ----------------------------------------------------------
    if cookies:
        headers["Cookie"] = "; ".join(c.strip().rstrip(";") for c in cookies if c.strip())

    # ---- Method / body ----------------------------------------------------
    data = "&".join(data_parts) if data_parts else ""
    has_data = bool(data_parts)
    if has_data and form_fields:
        warnings.append("Both -d and -F were given; only the -F form fields are imported.")
        has_data = False
        data = ""

    if get_mode and data:
        url += ("&" if "?" in url else "?") + data     # -G: data goes to the query string
        data, has_data = "", False

    if method is None:
        if head_mode:
            method = "HEAD"
        elif has_data or form_fields:
            method = "POST"
        else:
            method = "GET"
    if method not in HTTP_METHODS:
        warnings.append(f"Method '{method}' is not supported by KangPaket; using GET.")
        method = "GET"

    if json_mode:
        headers.setdefault("Content-Type", "application/json")
        headers.setdefault("Accept", "application/json")

    body_type, body_content, body_form = "none", "", {}
    ctype = next((v for k, v in headers.items() if k.lower() == "content-type"), "").lower()

    if form_fields:
        keys = [k for k, _ in form_fields]
        if len(set(keys)) != len(keys):
            warnings.append("Repeated form field names: only the last value of each is kept.")
        body_type, body_form = "form-data", dict(form_fields)
    elif has_data:
        is_form_ct = "x-www-form-urlencoded" in ctype
        if is_form_ct or (not ctype and _looks_like_form(data)):
            pairs = _parse_form_pairs(data)
            keys = [k for k, _ in pairs]
            if pairs and len(set(keys)) == len(keys):
                body_type, body_form = "x-www-form-urlencoded", dict(pairs)
            else:
                body_type, body_content = "raw", data
                if pairs:
                    warnings.append("Repeated form keys cannot be shown as a table; imported as raw body.")
        else:
            body_type, body_content = "raw", data

    # ---- Basic auth -------------------------------------------------------
    auth_type, auth_data = "none", {}
    if user is not None:
        uname, sep, pwd = user.partition(":")
        auth_type, auth_data = "basic", {"username": uname, "password": pwd}
        if not sep:
            warnings.append("-u without a password: curl would prompt for one; imported with an empty password.")

    # ---- URL -> base + query params --------------------------------------
    base, params = url, {}
    if "?" in url:
        base, _, query = url.partition("?")
        frag = ""
        if "#" in query:
            query, _, frag = query.partition("#")
            frag = "#" + frag
        pairs = urllib.parse.parse_qsl(query, keep_blank_values=True)
        keys = [k for k, _ in pairs]
        if pairs and len(set(keys)) == len(keys):
            params = dict(pairs)
            base += frag
        else:
            base = url                 # repeated keys can't live in a dict; keep the query in the URL
            if pairs:
                warnings.append("Repeated query keys kept inside the URL (Params table cannot hold duplicates).")

    parsed = urllib.parse.urlparse(base)
    short = parsed.path if parsed.path not in ("", "/") else parsed.netloc
    name = f"{method} {short}"[:60] or "Imported request"

    profile = RequestProfile(
        name=name,
        url=base,
        method=method,
        headers=headers,
        params=params,
        body_type=body_type,
        body_content=body_content,
        body_form=body_form,
        auth_type=auth_type,
        auth_data=auth_data,
        verify_ssl=not insecure,
    )
    return CurlImportResult(profile=profile, warnings=warnings)
