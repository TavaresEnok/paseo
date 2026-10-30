"""Loopback client for the account coordinator. Fail closed. No inference."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


class CapacityUnavailable(Exception):
    """The coordinator could not be trusted for this call."""


class Client:
    def __init__(self, config):
        if not isinstance(config, dict):
            raise CapacityUnavailable("broker config invalid")
        url = config.get("url")
        token_file = config.get("token_file")
        account_id = config.get("account_id")
        host_id = config.get("host_id")
        if not all(isinstance(item, str) and item.strip() for item in (url, token_file, account_id, host_id)):
            raise CapacityUnavailable("broker config invalid")
        parsed = urllib.parse.urlparse(url.strip())
        if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
            raise CapacityUnavailable("broker url must be loopback")
        self.url = url.strip().rstrip("/")
        self.token_file = token_file.strip()
        self.account_id = account_id.strip()
        self.host_id = host_id.strip()
        timeout = config.get("timeout", 5)
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or timeout <= 0:
            raise CapacityUnavailable("broker config invalid")
        self.timeout = float(timeout)

    def observe(self, catalog, limits):
        return self._call("POST", "/v1/observe", {"catalog": catalog, "limits": limits})

    def register(self, chat_id, candidates, replace=True):
        return self._call(
            "POST",
            "/v1/register",
            {"chat_id": chat_id, "candidates": candidates, "replace": bool(replace)},
        )

    def acquire(self, chat_id, task_id, role, request_id, metadata=None):
        body = {
            "chat_id": chat_id,
            "task_id": task_id,
            "role": role,
            "request_id": request_id,
            "metadata": metadata or {},
        }
        return self._call("POST", "/v1/acquire", body)

    def bind(self, lease_id, agent_id):
        return self._call("POST", "/v1/bind", {"lease_id": lease_id, "agent_id": agent_id})

    def release(self, lease_id, terminal_evidence):
        return self._call(
            "POST",
            "/v1/release",
            {"lease_id": lease_id, "terminal_evidence": terminal_evidence},
        )

    def heartbeat(self, chat_id=None):
        body = {}
        if chat_id is not None:
            body["chat_id"] = chat_id
        return self._call("POST", "/v1/heartbeat", body)

    def reconcile(self, known_lease_ids):
        return self._call("POST", "/v1/reconcile", {"known_lease_ids": list(known_lease_ids)})

    def status(self):
        query = urllib.parse.urlencode({"account_id": self.account_id, "host_id": self.host_id})
        return self._call("GET", "/v1/status?" + query, None)

    def _token(self):
        try:
            secret = Path(self.token_file).read_text(encoding="utf-8").strip()
        except OSError:
            raise CapacityUnavailable("broker unavailable") from None
        if not secret:
            raise CapacityUnavailable("broker unavailable")
        return secret

    def _call(self, method, path, payload):
        secret = self._token()
        data = None
        headers = {"Authorization": "Bearer " + secret, "Accept": "application/json"}
        if payload is not None:
            body = {"account_id": self.account_id, "host_id": self.host_id, **payload}
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(self.url + path, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read()
        except urllib.error.HTTPError:
            raise CapacityUnavailable("broker rejected the request") from None
        except Exception:
            raise CapacityUnavailable("broker unavailable") from None
        try:
            parsed = json.loads(raw.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError):
            raise CapacityUnavailable("broker response malformed") from None
        if not isinstance(parsed, dict):
            raise CapacityUnavailable("broker response malformed")
        return parsed
