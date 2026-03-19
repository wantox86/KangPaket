"""
KangPaket — Postman Collection importer.
Supports Postman Collection v2.0 and v2.1 JSON format.
"""
from __future__ import annotations

import json
import os
import urllib.parse
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.models.request_model import RequestProfile


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class PostmanImportResult:
    collection_name: str
    total_items: int
    profiles: list[RequestProfile]
    warnings: list[str]
    skipped: list[str]


class PostmanImportError(Exception):
    """Raised when the file is not a valid Postman Collection."""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_postman_file(path: str) -> PostmanImportResult:
    """
    Read a Postman Collection JSON file, validate, and convert all requests
    to RequestProfile objects.

    Raises PostmanImportError for invalid or unsupported files.
    """
    # Size warning threshold: 10 MB
    try:
        size = os.path.getsize(path)
    except OSError:
        size = 0

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise PostmanImportError(f"File cannot be read as JSON: {e}") from e
    except OSError as e:
        raise PostmanImportError(f"Cannot open file: {e}") from e

    parser = _PostmanParser(data)
    result = parser.parse()

    if result.total_items == 0:
        raise PostmanImportError(
            "Collection has no importable requests."
        )

    return result


def get_file_size_mb(path: str) -> float:
    try:
        return os.path.getsize(path) / (1024 * 1024)
    except OSError:
        return 0.0


# ---------------------------------------------------------------------------
# Internal parser
# ---------------------------------------------------------------------------

class _PostmanParser:
    def __init__(self, data: dict) -> None:
        self._data     = data
        self._warnings: list[str] = []
        self._skipped:  list[str] = []
        self._has_scripts   = False
        self._has_variables = False

    # ------------------------------------------------------------------
    # Entry point
    # ------------------------------------------------------------------

    def parse(self) -> PostmanImportResult:
        data = self._data

        # Validate top-level structure
        if not isinstance(data, dict):
            raise PostmanImportError("Unrecognized format — file is not a JSON object.")

        info = data.get("info")
        if not isinstance(info, dict):
            raise PostmanImportError(
                "Unrecognized format. Only Postman Collection v2.0/v2.1 is supported."
            )

        schema = info.get("schema", "")
        if "v2.0" in schema:
            version = "v2.0"
        elif "v2.1" in schema:
            version = "v2.1"
        else:
            raise PostmanImportError(
                "Unrecognized format. Only Postman Collection v2.0/v2.1 is supported."
            )

        collection_name = info.get("name", "Imported Collection").strip() or "Imported Collection"

        # Check top-level scripts (pre-request / test events on collection)
        if data.get("event"):
            self._has_scripts = True

        # Warn about collection-level variables
        if data.get("variable"):
            self._has_variables = True

        # Warn about auth at collection level
        col_auth = data.get("auth")

        # Parse items recursively
        items = data.get("item", [])
        if not isinstance(items, list):
            raise PostmanImportError("Collection has no valid items.")

        profiles: list[RequestProfile] = []
        self._parse_items(
            items,
            collection_name=collection_name,
            folder_path=[],
            col_auth=col_auth,
            profiles=profiles,
        )

        # Global warnings
        if self._has_scripts:
            self._warnings.append(
                "Pre-request scripts and test scripts are ignored (not supported in V1)."
            )
        if self._has_variables:
            self._warnings.append(
                "Collection variables are not converted. URLs/headers containing "
                "{{variable}} are left as-is."
            )

        return PostmanImportResult(
            collection_name=collection_name,
            total_items=len(profiles) + len(self._skipped),
            profiles=profiles,
            warnings=self._warnings,
            skipped=self._skipped,
        )

    # ------------------------------------------------------------------
    # Recursive item parser
    # ------------------------------------------------------------------

    def _parse_items(
        self,
        items: list,
        collection_name: str,
        folder_path: list[str],
        col_auth,
        profiles: list[RequestProfile],
    ) -> None:
        for item in items:
            if not isinstance(item, dict):
                continue

            # Check for pre/post scripts
            if item.get("event"):
                self._has_scripts = True

            # Sub-folder (has nested "item" list)
            if "item" in item:
                folder_name = item.get("name", "Folder")
                new_path    = folder_path + [folder_name]
                if len(new_path) > 3:
                    self._warnings.append(
                        f"Folder depth > 3 levels flattened: "
                        f"{' / '.join(new_path)}"
                    )
                sub_auth = item.get("auth") or col_auth
                self._parse_items(
                    item["item"],
                    collection_name=collection_name,
                    folder_path=new_path,
                    col_auth=sub_auth,
                    profiles=profiles,
                )
                continue

            # Leaf request item
            request_data = item.get("request")
            if not request_data:
                continue

            name = item.get("name", "").strip()

            try:
                profile, item_warnings = self._convert_request(
                    request_data=request_data,
                    name=name,
                    collection_name=collection_name,
                    folder_path=folder_path,
                    col_auth=col_auth,
                )
                self._warnings.extend(item_warnings)
                profiles.append(profile)
            except Exception as e:
                skip_name = name or str(request_data.get("url", "unknown"))
                self._skipped.append(skip_name)
                self._warnings.append(f"Skip '{skip_name}': {e}")

    # ------------------------------------------------------------------
    # Single request conversion
    # ------------------------------------------------------------------

    def _convert_request(
        self,
        request_data: dict | str,
        name: str,
        collection_name: str,
        folder_path: list[str],
        col_auth,
    ) -> tuple[RequestProfile, list[str]]:
        """Convert one Postman request dict to a RequestProfile."""
        warnings: list[str] = []

        # v2.0: request can be a plain URL string
        if isinstance(request_data, str):
            url = request_data
            return RequestProfile(
                name=name or url,
                collection=self._build_collection(collection_name, folder_path),
                method="GET",
                url=url,
            ), warnings

        # ── Method ──────────────────────────────────────────────────
        method = str(request_data.get("method", "GET")).upper()
        if method not in ("GET","POST","PUT","PATCH","DELETE","HEAD","OPTIONS"):
            warnings.append(f"'{name}': unknown method '{method}', defaulting to GET.")
            method = "GET"

        # ── URL ─────────────────────────────────────────────────────
        url_raw, params, url_warnings = self._parse_url(request_data.get("url", ""), name)
        warnings.extend(url_warnings)

        if not name:
            name = url_raw or "Untitled"
            warnings.append(f"Request without a name — using URL as name: '{name}'.")

        # ── Headers ─────────────────────────────────────────────────
        headers: dict[str, str] = {}
        for h in (request_data.get("header") or []):
            if not isinstance(h, dict):
                continue
            if h.get("disabled"):
                continue
            k = h.get("key", "").strip()
            v = h.get("value", "").strip()
            if not k:
                continue
            if "{{" in v:
                warnings.append(
                    f"'{name}': header '{k}' contains a Postman variable — left as-is."
                )
            headers[k] = v

        # ── Body ────────────────────────────────────────────────────
        body_type, body_content, body_form, body_warnings = self._parse_body(
            request_data.get("body"), name
        )
        warnings.extend(body_warnings)

        # ── Auth ────────────────────────────────────────────────────
        # Priority: request-level auth > folder/collection auth
        raw_auth = request_data.get("auth") or col_auth
        auth_type, auth_data, auth_warnings = self._parse_auth(raw_auth, name)
        warnings.extend(auth_warnings)

        # ── Collection label ────────────────────────────────────────
        collection_label = self._build_collection(collection_name, folder_path)

        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        profile = RequestProfile(
            id=str(uuid.uuid4()),
            name=name,
            collection=collection_label,
            method=method,
            url=url_raw,
            headers=headers,
            params=params,
            body_type=body_type,
            body_content=body_content,
            body_form=body_form,
            auth_type=auth_type,
            auth_data=auth_data,
            created_at=now,
            updated_at=now,
        )
        return profile, warnings

    # ------------------------------------------------------------------
    # URL parsing
    # ------------------------------------------------------------------

    def _parse_url(
        self, url_field, item_name: str
    ) -> tuple[str, dict[str, str], list[str]]:
        warnings: list[str] = []
        params: dict[str, str] = {}

        if not url_field:
            return "", params, warnings

        # v2.0: URL is a plain string
        if isinstance(url_field, str):
            raw = url_field
        else:
            # v2.1: URL is an object with .raw and optionally .query
            raw = url_field.get("raw", "")

            # Query params from structured field
            for q in (url_field.get("query") or []):
                if not isinstance(q, dict):
                    continue
                if q.get("disabled"):
                    continue
                k = q.get("key", "").strip()
                v = q.get("value", "") or ""
                if k:
                    params[k] = v

            # If no structured query but params embedded in raw URL, parse from raw
            if not params and "?" in raw:
                try:
                    parsed = urllib.parse.urlparse(raw)
                    for k, v in urllib.parse.parse_qsl(parsed.query):
                        params[k] = v
                except Exception:
                    pass

        if "{{" in raw:
            warnings.append(
                f"'{item_name}': URL contains a Postman variable ({{...}}) — left as-is."
            )

        return raw, params, warnings

    # ------------------------------------------------------------------
    # Body parsing
    # ------------------------------------------------------------------

    def _parse_body(
        self, body: dict | None, item_name: str
    ) -> tuple[str, str, dict, list[str]]:
        warnings: list[str] = []
        body_content = ""
        body_form: dict[str, str] = {}

        if not body or not isinstance(body, dict):
            return "none", body_content, body_form, warnings

        mode = body.get("mode", "none")

        if mode == "raw":
            raw_text = body.get("raw", "")
            # Check language hint for Content-Type
            lang = (body.get("options") or {}).get("raw", {}).get("language", "")
            # We just store raw content; Content-Type header should already be set
            return "raw", raw_text, body_form, warnings

        elif mode == "urlencoded":
            for entry in (body.get("urlencoded") or []):
                if not isinstance(entry, dict) or entry.get("disabled"):
                    continue
                k = entry.get("key", "").strip()
                v = entry.get("value", "") or ""
                if k:
                    body_form[k] = v
            return "x-www-form-urlencoded", "", body_form, warnings

        elif mode == "formdata":
            for entry in (body.get("formdata") or []):
                if not isinstance(entry, dict) or entry.get("disabled"):
                    continue
                if entry.get("type") == "file":
                    warnings.append(
                        f"'{item_name}': file upload in body ignored (not supported in V1)."
                    )
                    continue
                k = entry.get("key", "").strip()
                v = entry.get("value", "") or ""
                if k:
                    body_form[k] = v
            return "form-data", "", body_form, warnings

        elif mode == "graphql":
            gql = body.get("graphql") or {}
            payload = json.dumps({
                "query":     gql.get("query", ""),
                "variables": gql.get("variables", {}),
            }, ensure_ascii=False)
            warnings.append(
                f"'{item_name}': GraphQL body converted to raw JSON."
            )
            return "raw", payload, body_form, warnings

        elif mode == "file":
            warnings.append(
                f"'{item_name}': file upload body ignored (not supported in V1)."
            )
            return "none", "", body_form, warnings

        # none or unknown
        return "none", "", body_form, warnings

    # ------------------------------------------------------------------
    # Auth parsing
    # ------------------------------------------------------------------

    def _parse_auth(
        self, auth: dict | None, item_name: str
    ) -> tuple[str, dict, list[str]]:
        warnings: list[str] = []
        auth_data: dict[str, str] = {}

        if not auth or not isinstance(auth, dict):
            return "none", auth_data, warnings

        auth_type_raw = auth.get("type", "noauth")

        if auth_type_raw in ("noauth", "none", None):
            return "none", auth_data, warnings

        elif auth_type_raw == "bearer":
            token = self._find_auth_value(auth.get("bearer"), "token")
            auth_data["token"] = token
            return "bearer", auth_data, warnings

        elif auth_type_raw == "basic":
            auth_data["username"] = self._find_auth_value(auth.get("basic"), "username")
            auth_data["password"] = self._find_auth_value(auth.get("basic"), "password")
            return "basic", auth_data, warnings

        elif auth_type_raw == "apikey":
            auth_data["key"]   = self._find_auth_value(auth.get("apikey"), "key")
            auth_data["value"] = self._find_auth_value(auth.get("apikey"), "value")
            loc = self._find_auth_value(auth.get("apikey"), "in") or "header"
            auth_data["in"] = loc
            return "api-key", auth_data, warnings

        else:
            warnings.append(
                f"'{item_name}': auth type '{auth_type_raw}' is not supported — ignored."
            )
            return "none", auth_data, warnings

    @staticmethod
    def _find_auth_value(entries: list | None, key: str) -> str:
        """Find a value by key in Postman auth key-value array."""
        if not entries or not isinstance(entries, list):
            return ""
        for entry in entries:
            if isinstance(entry, dict) and entry.get("key") == key:
                return str(entry.get("value", ""))
        return ""

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_collection(collection_name: str, folder_path: list[str]) -> str:
        parts = [collection_name] + folder_path
        return " / ".join(parts)
