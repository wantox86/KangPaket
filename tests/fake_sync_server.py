"""In-memory fake of the KangPaket-server sync contract, served through httpx.MockTransport."""
import json
import re
import secrets

import httpx

UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")


def _compact(raw) -> str:
    return json.dumps(raw, ensure_ascii=False, separators=(",", ":"))


class FakeSyncServer:
    def __init__(self, users: dict[str, str] | None = None) -> None:
        self.users = users or {"alice": "correct-horse-1"}
        self.down = False
        self.fail_status: int | None = None
        self.access: dict[str, str] = {}
        self.refresh: dict[str, str] = {}
        self.records: dict[str, dict[tuple, dict]] = {}
        self.version: dict[str, int] = {}
        self.push_calls: list[dict] = []
        self.pull_calls: list[int] = []
        self.requests: list[tuple[str, str]] = []
        self.pull_page_cap: int | None = None
        self.transport = httpx.MockTransport(self.handle)

    # ---- helpers for tests --------------------------------------------

    def expire_access_tokens(self) -> None:
        self.access.clear()

    def revoke_refresh_tokens(self) -> None:
        self.refresh.clear()

    def live(self, user: str, kind: str) -> dict[str, dict]:
        return {k[1]: v for k, v in self.records.get(user, {}).items() if k[0] == kind and not v["deleted"]}

    def tombstones(self, user: str, kind: str) -> set[str]:
        return {k[1] for k, v in self.records.get(user, {}).items() if k[0] == kind and v["deleted"]}

    def seed(self, user: str, kind: str, item_id: str, label: str, payload: dict, ts: int, deleted=False) -> None:
        self._write(user, kind, item_id, label, None if deleted else payload, ts, deleted)

    # ---- http ----------------------------------------------------------

    def handle(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        self.requests.append((request.method, path))
        if self.down:
            raise httpx.ConnectError("down", request=request)
        if self.fail_status:
            return httpx.Response(self.fail_status, json={"error": "boom"})
        body = json.loads(request.content) if request.content else {}
        if path == "/auth/login":
            if self.users.get(body.get("username")) != body.get("password"):
                return httpx.Response(401, json={"error": "invalid_credentials"})
            return self._issue(body["username"])
        if path == "/auth/refresh":
            user = self.refresh.pop(body.get("refresh_token", ""), None)
            if not user:
                return httpx.Response(401, json={"error": "invalid_token"})
            return self._issue(user)
        if path == "/auth/logout":
            self.refresh.pop(body.get("refresh_token", ""), None)
            return httpx.Response(204)
        auth = request.headers.get("Authorization", "")
        user = self.access.get(auth.removeprefix("Bearer "))
        if not user:
            return httpx.Response(401, json={"error": "unauthorized"})
        if path == "/sync/pull":
            return self._pull(user, request)
        if path == "/sync/push":
            if len(request.content) > 5 << 20:
                return httpx.Response(413, json={"error": "payload_too_large"})
            return self._push(user, body)
        return httpx.Response(404)

    def _issue(self, user: str) -> httpx.Response:
        at, rt = "at-" + secrets.token_hex(8), "rt-" + secrets.token_hex(8)
        self.access[at] = user
        self.refresh[rt] = user
        return httpx.Response(200, json={"access_token": at, "refresh_token": rt, "expires_in": 900,
                                         "user": {"username": user}})

    def _pull(self, user: str, request: httpx.Request) -> httpx.Response:
        since = int(request.url.params.get("since", 0))
        limit = int(request.url.params.get("limit", 500))
        if self.pull_page_cap:
            limit = min(limit, self.pull_page_cap)
        self.pull_calls.append(since)
        items = sorted((v for v in self.records.get(user, {}).values() if v["server_version"] > since),
                       key=lambda v: v["server_version"])
        page = items[:limit]
        cursor = page[-1]["server_version"] if page else since
        return httpx.Response(200, json={"items": [self._wire(v) for v in page], "cursor": cursor,
                                         "has_more": len(items) > len(page)})

    @staticmethod
    def _wire(rec: dict) -> dict:
        out = {k: rec[k] for k in ("kind", "id", "client_updated_at", "deleted", "server_version")}
        if not rec["deleted"]:
            out["label"] = rec["label"]
            out["payload"] = rec["payload"]
        return out

    def _write(self, user, kind, item_id, label, payload, ts, deleted) -> dict:
        self.version[user] = self.version.get(user, 0) + 1
        rec = {"kind": kind, "id": item_id, "label": label, "payload": payload, "client_updated_at": ts,
               "deleted": deleted, "server_version": self.version[user]}
        self.records.setdefault(user, {})[(kind, item_id)] = rec
        return rec

    def _push(self, user: str, body: dict) -> httpx.Response:
        self.push_calls.append(body)
        sets = [("profile", body.get("profiles", [])), ("environment", body.get("environments", []))]
        if sum(len(s) for _, s in sets) > 500:
            return httpx.Response(413, json={"error": "too_many_items"})
        parsed = []
        seen = set()
        for kind, items in sets:
            for p in items:
                if not UUID_RE.match(p.get("id", "")):
                    return httpx.Response(400, json={"error": "invalid_id"})
                item_id = p["id"].lower()
                if (kind, item_id) in seen:
                    return httpx.Response(400, json={"error": "duplicate_id"})
                seen.add((kind, item_id))
                if p.get("client_updated_at", 0) <= 0:
                    return httpx.Response(400, json={"error": "invalid_client_updated_at"})
                label = p.get("collection" if kind == "profile" else "name", "")
                deleted = bool(p.get("deleted"))
                payload = None
                if not deleted:
                    payload = p.get("payload")
                    if not isinstance(payload, dict):
                        return httpx.Response(400, json={"error": "invalid_payload"})
                    if len(_compact(payload).encode()) > 256 << 10:
                        return httpx.Response(413, json={"error": "item_too_large"})
                parsed.append((kind, item_id, label, payload, p["client_updated_at"], deleted))
        results = []
        for kind, item_id, label, payload, ts, deleted in parsed:
            cur = self.records.get(user, {}).get((kind, item_id))
            decision = self._decide(cur, label, payload, ts, deleted)
            if decision == "apply":
                rec = self._write(user, kind, item_id, label, payload, ts, deleted)
                results.append({"kind": kind, "id": item_id, "status": "applied", "server_version": rec["server_version"]})
            elif decision == "unchanged":
                results.append({"kind": kind, "id": item_id, "status": "skipped", "server_version": cur["server_version"]})
            else:
                results.append({"kind": kind, "id": item_id, "status": "conflict",
                                "server_version": cur["server_version"], "server": self._wire(cur)})
        return httpx.Response(200, json={"results": results, "cursor": self.version.get(user, 0)})

    @staticmethod
    def _decide(cur, label, payload, ts, deleted) -> str:
        if cur is None:
            return "apply"
        if ts > cur["client_updated_at"]:
            return "apply"
        if ts < cur["client_updated_at"]:
            return "conflict"
        if deleted == cur["deleted"] and (deleted or (label == cur["label"] and _compact(payload) == _compact(cur["payload"]))):
            return "unchanged"
        if deleted != cur["deleted"]:
            return "apply" if deleted else "conflict"
        new_key = label + "\0" + _compact(payload)
        cur_key = cur["label"] + "\0" + _compact(cur["payload"])
        return "apply" if new_key.encode() > cur_key.encode() else "conflict"
