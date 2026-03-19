"""
KangPaket — HTTP request engine using httpx (synchronous).
"""
import httpx
from datetime import datetime, timezone

from app.config import USER_AGENT
from app.models.request_model import RequestProfile
from app.models.response_model import ResponseResult


class HttpClient:
    """Executes HTTP requests based on a RequestProfile and returns ResponseResult."""

    def send(
        self,
        profile: RequestProfile,
        default_timeout: float = 30.0,
        proxy_enabled: bool = False,
        proxy_http: str = "",
        proxy_https: str = "",
    ) -> ResponseResult:
        timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

        try:
            timeout = profile.timeout if profile.timeout is not None else default_timeout
            # timeout=0 means no timeout
            httpx_timeout = None if timeout == 0 else timeout

            headers = self._build_headers(profile)
            auth    = self._build_auth(profile)
            content, data, files = self._build_body(profile)

            # Build proxy config
            proxies: dict[str, str] | None = None
            if proxy_enabled:
                proxies = {}
                if proxy_http:
                    proxies["http://"]  = proxy_http
                if proxy_https:
                    proxies["https://"] = proxy_https
                if not proxies:
                    proxies = None

            with httpx.Client(
                timeout=httpx_timeout,
                follow_redirects=profile.follow_redirects,
                verify=profile.verify_ssl,
                proxy=proxies.get("https://") or proxies.get("http://") if proxies else None,
            ) as client:
                response = client.request(
                    method=profile.method.upper(),
                    url=self._build_url(profile),
                    headers=headers,
                    auth=auth,
                    content=content,
                    data=data,
                    files=files,
                )

            elapsed_ms = response.elapsed.total_seconds() * 1000
            size_bytes = len(response.content)

            # Decode body safely
            try:
                body = response.text
            except Exception:
                body = response.content.decode("utf-8", errors="replace")

            return ResponseResult(
                status_code=response.status_code,
                status_text=response.reason_phrase,
                headers=dict(response.headers),
                body=body,
                elapsed_ms=elapsed_ms,
                size_bytes=size_bytes,
                timestamp=timestamp,
                error=None,
            )

        except httpx.TimeoutException as e:
            return ResponseResult(
                status_code=0,
                status_text="TIMEOUT",
                timestamp=timestamp,
                error=f"Request timed out: {e}",
            )
        except httpx.ConnectError as e:
            return ResponseResult(
                status_code=0,
                status_text="CONNECTION ERROR",
                timestamp=timestamp,
                error=f"Connection refused or host unreachable: {e}",
            )
        except httpx.InvalidURL as e:
            return ResponseResult(
                status_code=0,
                status_text="INVALID URL",
                timestamp=timestamp,
                error=f"Invalid URL: {e}",
            )
        except httpx.SSLError as e:
            return ResponseResult(
                status_code=0,
                status_text="SSL ERROR",
                timestamp=timestamp,
                error=f"SSL error: {e}. Coba nonaktifkan Verify SSL di tab Settings.",
            )
        except Exception as e:
            return ResponseResult(
                status_code=0,
                status_text="ERROR",
                timestamp=timestamp,
                error=f"Unexpected error: {type(e).__name__}: {e}",
            )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_url(self, profile: RequestProfile) -> str:
        url = profile.url.strip()
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        if profile.params:
            import urllib.parse
            qs = urllib.parse.urlencode(profile.params)
            separator = "&" if "?" in url else "?"
            url = url + separator + qs
        return url

    def _build_headers(self, profile: RequestProfile) -> dict[str, str]:
        headers: dict[str, str] = {"User-Agent": USER_AGENT}
        headers.update(profile.headers)

        # Auth headers (bearer / api-key inject into headers here)
        if profile.auth_type == "bearer":
            token = profile.auth_data.get("token", "")
            headers["Authorization"] = f"Bearer {token}"
        elif profile.auth_type == "api-key":
            key_name  = profile.auth_data.get("key", "X-API-Key")
            key_value = profile.auth_data.get("value", "")
            location  = profile.auth_data.get("in", "header")
            if location == "header":
                headers[key_name] = key_value

        return headers

    def _build_auth(self, profile: RequestProfile) -> httpx.BasicAuth | None:
        if profile.auth_type == "basic":
            username = profile.auth_data.get("username", "")
            password = profile.auth_data.get("password", "")
            return httpx.BasicAuth(username, password)
        return None

    def _build_body(
        self, profile: RequestProfile
    ) -> tuple[bytes | None, dict | None, dict | None]:
        """Returns (content, data, files) tuple for httpx.request()."""
        body_type = profile.body_type

        if body_type == "raw":
            return profile.body_content.encode("utf-8"), None, None

        elif body_type == "x-www-form-urlencoded":
            return None, dict(profile.body_form), None

        elif body_type == "form-data":
            files = {k: (None, v) for k, v in profile.body_form.items()}
            return None, None, files

        # none or anything else
        return None, None, None
