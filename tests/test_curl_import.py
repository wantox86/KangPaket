"""Unit tests for app/core/curl_import.py (pure parser, no GUI, no network)."""
import pytest

from app.core.curl_import import CurlParseError, parse_curl, tokenize


def p(cmd):
    return parse_curl(cmd).profile


def test_simple_get():
    r = p("curl https://example.com/api")
    assert (r.method, r.url, r.body_type) == ("GET", "https://example.com/api", "none")
    assert r.verify_ssl is True and r.name == "GET /api"


def test_url_without_scheme_gets_http():
    assert p("curl example.com/x").url == "http://example.com/x"
    assert p("curl localhost:8080/x").url == "http://localhost:8080/x"


def test_url_option_and_quotes():
    assert p("curl --url 'https://a.test/x'").url == "https://a.test/x"


def test_query_params_extracted():
    r = p("curl 'https://a.test/s?q=hello+world&page=2&empty='")
    assert r.url == "https://a.test/s"
    assert r.params == {"q": "hello world", "page": "2", "empty": ""}


def test_duplicate_query_keys_stay_in_url():
    res = parse_curl("curl 'https://a.test/s?a=1&a=2'")
    assert res.profile.url == "https://a.test/s?a=1&a=2" and res.profile.params == {}
    assert any("Repeated query" in w for w in res.warnings)


def test_explicit_method_and_headers():
    r = p("curl -X PUT -H 'Accept: text/plain' --header \"X-Id: 7\" https://a.test")
    assert r.method == "PUT"
    assert r.headers == {"Accept": "text/plain", "X-Id": "7"}


def test_data_defaults_to_post_json_raw():
    r = p("""curl https://a.test -H 'Content-Type: application/json' -d '{"a": 1}'""")
    assert r.method == "POST" and r.body_type == "raw" and r.body_content == '{"a": 1}'


def test_x_overrides_post_default():
    assert p("curl -X PATCH -d 'x=1' https://a.test").method == "PATCH"


@pytest.mark.parametrize("flag", ["-d", "--data", "--data-raw", "--data-binary", "--data-ascii"])
def test_data_variants(flag):
    r = p(f"curl {flag} 'hello' https://a.test")
    assert r.method == "POST" and r.body_content == "hello" and r.body_type == "raw"


def test_urlencoded_body_becomes_form_table():
    r = p("curl -d 'a=1&b=two%20words' https://a.test")
    assert r.body_type == "x-www-form-urlencoded"
    assert r.body_form == {"a": "1", "b": "two words"}


def test_multiple_d_joined_with_ampersand():
    r = p("curl -d a=1 -d b=2 https://a.test")
    assert r.body_form == {"a": "1", "b": "2"}


def test_data_urlencode():
    r = p("curl --data-urlencode 'q=a b&c' https://a.test")
    assert r.body_form == {"q": "a b&c"}


def test_get_flag_moves_data_to_query():
    r = p("curl -G -d 'a=1' --data-urlencode 'b=x y' https://a.test/s")
    assert r.method == "GET" and r.body_type == "none"
    assert r.params == {"a": "1", "b": "x y"}


def test_basic_auth():
    r = p("curl -u alice:s3cret https://a.test")
    assert r.auth_type == "basic" and r.auth_data == {"username": "alice", "password": "s3cret"}


def test_basic_auth_password_with_colon_and_missing_password():
    assert p("curl --user 'a:b:c' https://a.test").auth_data["password"] == "b:c"
    res = parse_curl("curl -u bob https://a.test")
    assert res.profile.auth_data == {"username": "bob", "password": ""} and res.warnings


def test_form_fields():
    r = p("curl -F name=Ann -F 'note=hi there' https://a.test/up")
    assert r.method == "POST" and r.body_type == "form-data"
    assert r.body_form == {"name": "Ann", "note": "hi there"}


def test_form_file_not_read_warns():
    res = parse_curl("curl -F file=@/etc/passwd https://a.test")
    assert res.profile.body_form == {"file": "@/etc/passwd"}
    assert any("file uploads" in w for w in res.warnings)


def test_data_at_file_not_read():
    res = parse_curl("curl -d @secrets.json https://a.test")
    assert res.profile.body_type == "none" and any("not supported" in w for w in res.warnings)


def test_cookie_option_and_cookie_header_merge():
    r = p("curl -b 'a=1; b=2' -H 'Cookie: c=3' https://a.test")
    assert r.headers["Cookie"] == "a=1; b=2; c=3"   # merged in command-line order


def test_cookie_file_is_skipped():
    res = parse_curl("curl -b cookies.txt https://a.test")
    assert "Cookie" not in res.profile.headers and res.warnings


def test_insecure_sets_verify_ssl_false_and_ignored_flags():
    res = parse_curl("curl -k --compressed -L -s -S -v https://a.test")
    assert res.profile.verify_ssl is False
    assert res.profile.method == "GET"


def test_clustered_short_flags_and_attached_values():
    r = p("curl -sSLXPOST -H'A: b' -dx=1 https://a.test")
    assert r.method == "POST" and r.headers == {"A": "b"} and r.body_form == {"x": "1"}


def test_head_flag():
    assert p("curl -I https://a.test").method == "HEAD"


def test_user_agent_and_referer():
    r = p("curl -A 'Bot/1' -e https://r.test https://a.test")
    assert r.headers == {"User-Agent": "Bot/1", "Referer": "https://r.test"}


def test_json_option():
    r = p("""curl --json '{"a":1}' https://a.test""")
    assert r.method == "POST" and r.body_content == '{"a":1}'
    assert r.headers["Content-Type"] == "application/json"


def test_line_continuations_lf_and_crlf():
    cmd = "curl 'https://a.test/x' \\\n  -H 'A: 1' \\\r\n  -X DELETE"
    r = p(cmd)
    assert r.method == "DELETE" and r.headers == {"A": "1"}


def test_double_quote_escapes():
    r = p(r'''curl -d "{\"k\": \"v\"}" https://a.test''')
    assert r.body_content == '{"k": "v"}'


def test_ansi_c_quoting():
    r = p(r"""curl -X POST --data-raw $'{"a":"line1\nline2","q":"it\'s","u":"é\x41"}' https://a.test""")
    assert r.body_content == '{"a":"line1\nline2","q":"it\'s","u":"éA"}'


def test_chrome_copy_as_curl_bash():
    cmd = """curl 'https://api.example.com/v1/items?limit=10' \\
  -H 'accept: application/json, text/plain, */*' \\
  -H 'accept-language: en-US,en;q=0.9' \\
  -H 'authorization: Bearer abc.def.ghi' \\
  -H 'content-type: application/json' \\
  -b 'session=xyz; theme=dark' \\
  -H 'origin: https://app.example.com' \\
  -H 'user-agent: Mozilla/5.0 (Macintosh)' \\
  --data-raw '{"name":"it'\\''s"}' \\
  --compressed"""
    r = p(cmd)
    assert r.method == "POST" and r.url == "https://api.example.com/v1/items"
    assert r.params == {"limit": "10"}
    assert r.headers["authorization"] == "Bearer abc.def.ghi"
    assert r.headers["Cookie"] == "session=xyz; theme=dark"
    assert r.body_content == '{"name":"it\'s"}'


def test_firefox_copy_as_curl_bash():
    cmd = ("curl 'https://a.test/api' -X POST -H 'User-Agent: Mozilla/5.0' "
           "-H 'Content-Type: application/x-www-form-urlencoded' "
           "-H 'Cookie: a=1' --data-raw 'user=me&pw=p%40ss'")
    r = p(cmd)
    assert r.body_type == "x-www-form-urlencoded" and r.body_form == {"user": "me", "pw": "p@ss"}
    assert r.headers["Cookie"] == "a=1"


def test_prompt_prefix_tolerated():
    assert p("$ curl https://a.test").url == "https://a.test"


def test_unknown_option_warns_but_parses():
    res = parse_curl("curl --frobnicate https://a.test")
    assert res.profile.url == "https://a.test" and any("Unknown option" in w for w in res.warnings)


def test_unsupported_method_falls_back_with_warning():
    res = parse_curl("curl -X PURGE https://a.test")
    assert res.profile.method == "GET" and any("PURGE" in w for w in res.warnings)


def test_malformed_header_warns():
    res = parse_curl("curl -H 'nocolon' https://a.test")
    assert res.profile.headers == {} and res.warnings


def test_nothing_is_executed_or_read(tmp_path):
    marker = tmp_path / "pwned"
    parse_curl(f"curl 'https://a.test/$(touch {marker})' -d @{marker}")
    assert not marker.exists()


@pytest.mark.parametrize("bad, fragment", [
    ("", "empty"),
    ("   \n  ", "empty"),
    ("wget https://a.test", "curl"),
    ("curl", "No URL"),
    ("curl -X POST", "No URL"),
    ("curl -H", "needs a value"),
    ("curl 'https://a.test", "Unterminated single"),
    ('curl "https://a.test', "Unterminated double"),
    ("curl ftp://a.test/file", "scheme"),
    ("curl 'not a url with spaces'", "URL"),
    ("curl $'abc", "Unterminated"),
])
def test_bad_input_raises_clear_error(bad, fragment):
    with pytest.raises(CurlParseError) as exc:
        parse_curl(bad)
    assert fragment.lower() in str(exc.value).lower()


def test_tokenize_basic():
    assert tokenize("a 'b c' \"d e\" f\\ g") == ["a", "b c", "d e", "f g"]
