from __future__ import annotations

import json
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

from .models import MemoryScope, MemoryType, to_dict, utc_now
from .runtime import build_amos


class AmosHandler(BaseHTTPRequestHandler):
    amos = build_amos()

    def do_GET(self) -> None:
        try:
            parsed = urlparse(self.path)
            query = {key: values[0] for key, values in parse_qs(parsed.query).items()}
            parts = [part for part in parsed.path.split("/") if part]

            if parsed.path == "/health":
                dependencies = self.amos.health()
                status = HTTPStatus.OK if all(dependencies.values()) else HTTPStatus.SERVICE_UNAVAILABLE
                self._send(status, {"status": "ok" if status == HTTPStatus.OK else "degraded", "dependencies": dependencies})
                return
            if len(parts) == 3 and parts[:2] == ["v1", "memories"]:
                memory = self.amos.get_memory(parts[2])
                self._send(HTTPStatus.OK, memory) if memory else self._send(HTTPStatus.NOT_FOUND, {"error": "not found"})
                return
            if len(parts) == 4 and parts[:2] == ["v1", "memories"] and parts[3] == "explain":
                self._required(query, "tenant_id")
                self._send(HTTPStatus.OK, self.amos.explain_memory(tenant_id=query["tenant_id"], memory_id=parts[2]))
                return
            if parsed.path == "/v1/timeline":
                self._required(query, "tenant_id")
                result = self.amos.get_timeline(
                    tenant_id=query["tenant_id"],
                    entity=query.get("entity"),
                    attribute=query.get("attribute"),
                )
                self._send(HTTPStatus.OK, result)
                return
            if parsed.path == "/v1/relationships":
                self._required(query, "tenant_id", "node")
                self._send(
                    HTTPStatus.OK,
                    self.amos.get_relationships(tenant_id=query["tenant_id"], node=query["node"]),
                )
                return
            if parsed.path == "/v1/events":
                self._required(query, "tenant_id")
                self._send(HTTPStatus.OK, self.amos.events.events(query["tenant_id"]))
                return
            self._send(HTTPStatus.NOT_FOUND, {"error": "not found"})
        except (ValueError, KeyError) as error:
            self._send(HTTPStatus.BAD_REQUEST, {"error": str(error)})

    def do_POST(self) -> None:
        try:
            body = self._body()
            path = urlparse(self.path).path

            if path == "/v1/memories/assess":
                self._required(body, "content")
                decision = self.amos.assess_memory(
                    content=body["content"],
                    type=MemoryType(body.get("type", "OBSERVATION")),
                    importance=float(body.get("importance", 0.5)),
                    confidence=float(body.get("confidence", 1.0)),
                )
                self._send(HTTPStatus.OK, decision)
                return
            if path == "/v1/memories":
                self._required(body, "tenant_id", "content")
                memory = self.amos.remember(
                    tenant_id=body["tenant_id"],
                    content=body["content"],
                    type=MemoryType(body.get("type", "OBSERVATION")),
                    agent_id=body.get("agent_id"),
                    scope=MemoryScope(body.get("scope", "PRIVATE")),
                    importance=float(body.get("importance", 0.5)),
                    confidence=float(body.get("confidence", 1.0)),
                    metadata=body.get("metadata"),
                )
                self._send(HTTPStatus.CREATED, memory)
                return
            if path == "/v1/recall":
                self._required(body, "tenant_id", "query")
                result = self.amos.recall(
                    tenant_id=body["tenant_id"],
                    query=body["query"],
                    limit=int(body.get("limit", 10)),
                )
                self._send(HTTPStatus.OK, result)
                return
            if path == "/v1/context":
                self._required(body, "tenant_id", "query")
                result = self.amos.get_context(
                    tenant_id=body["tenant_id"],
                    query=body["query"],
                    token_budget=int(body.get("token_budget", 300)),
                )
                self._send(HTTPStatus.OK, result)
                return
            if path == "/v1/facts":
                self._required(body, "tenant_id", "entity", "attribute", "value", "source")
                fact = self.amos.update_fact(
                    tenant_id=body["tenant_id"],
                    entity=body["entity"],
                    attribute=body["attribute"],
                    value=body["value"],
                    valid_from=self._datetime(body.get("valid_from")),
                    source=body["source"],
                    memory_id=body.get("memory_id"),
                    confidence=float(body.get("confidence", 1.0)),
                )
                self._send(HTTPStatus.CREATED, fact)
                return
            if path == "/v1/relationships":
                self._required(body, "tenant_id", "source", "relation", "target")
                relationship = self.amos.add_relationship(
                    tenant_id=body["tenant_id"],
                    source=body["source"],
                    relation=body["relation"],
                    target=body["target"],
                    memory_id=body.get("memory_id"),
                    confidence=float(body.get("confidence", 1.0)),
                    metadata=body.get("metadata"),
                )
                self._send(HTTPStatus.CREATED, relationship)
                return
            if path == "/v1/consolidations":
                self._required(body, "tenant_id", "source_memory_ids", "content")
                memory = self.amos.consolidate(
                    tenant_id=body["tenant_id"],
                    source_memory_ids=body["source_memory_ids"],
                    content=body["content"],
                    type=MemoryType(body.get("type", "SUMMARY")),
                    confidence=float(body.get("confidence", 0.8)),
                    model=body.get("model"),
                )
                self._send(HTTPStatus.CREATED, memory)
                return
            if path == "/v1/scheduler/run":
                self._required(body, "tenant_id")
                self._send(HTTPStatus.OK, self.amos.run_scheduler(tenant_id=body["tenant_id"]))
                return
            parts = [part for part in path.split("/") if part]
            if len(parts) == 4 and parts[:2] == ["v1", "memories"] and parts[3] == "process":
                self._required(body, "tenant_id")
                report = self.amos.process_memory(
                    tenant_id=body["tenant_id"],
                    memory_id=parts[2],
                    force=bool(body.get("force", False)),
                )
                self._send(HTTPStatus.OK, report)
                return
            self._send(HTTPStatus.NOT_FOUND, {"error": "not found"})
        except (ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
            self._send(HTTPStatus.BAD_REQUEST, {"error": str(error)})

    def do_DELETE(self) -> None:
        try:
            body = self._body()
            parts = [part for part in urlparse(self.path).path.split("/") if part]
            if len(parts) == 3 and parts[:2] == ["v1", "memories"]:
                self._required(body, "tenant_id")
                forgotten = self.amos.forget(
                    tenant_id=body["tenant_id"],
                    memory_id=parts[2],
                    reason=body.get("reason", "requested"),
                    force=bool(body.get("force", False)),
                )
                self._send(HTTPStatus.OK, {"forgotten": forgotten})
                return
            self._send(HTTPStatus.NOT_FOUND, {"error": "not found"})
        except (ValueError, KeyError, json.JSONDecodeError) as error:
            self._send(HTTPStatus.BAD_REQUEST, {"error": str(error)})

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length == 0:
            return {}
        return json.loads(self.rfile.read(length))

    def _send(self, status: HTTPStatus, body: Any) -> None:
        encoded = json.dumps(to_dict(body), separators=(",", ":")).encode()
        self.send_response(status.value)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    @staticmethod
    def _required(body: dict[str, Any], *keys: str) -> None:
        missing = [key for key in keys if key not in body or body[key] in (None, "")]
        if missing:
            raise ValueError(f"missing required fields: {', '.join(missing)}")

    @staticmethod
    def _datetime(value: str | None) -> datetime:
        if value is None:
            return utc_now()
        return datetime.fromisoformat(value.replace("Z", "+00:00"))


def main() -> None:
    address = ("127.0.0.1", 8080)
    print(f"AMOS listening on http://{address[0]}:{address[1]}")
    ThreadingHTTPServer(address, AmosHandler).serve_forever()


if __name__ == "__main__":
    main()
