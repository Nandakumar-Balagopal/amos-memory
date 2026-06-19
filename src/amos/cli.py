from __future__ import annotations

import argparse
import json
from typing import Any

from .models import MemoryScope, MemoryType, to_dict
from .runtime import build_amos


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="amos", description="AMOS memory service tools")
    subcommands = parser.add_subparsers(dest="command")

    subcommands.add_parser("serve", help="Run the HTTP API server")
    subcommands.add_parser("health", help="Check configured storage dependencies")

    assess = subcommands.add_parser("assess", help="Assess whether content should be stored")
    assess.add_argument("content")
    assess.add_argument("--type", default="OBSERVATION", choices=[item.value for item in MemoryType])
    assess.add_argument("--importance", type=float, default=0.5)
    assess.add_argument("--confidence", type=float, default=1.0)

    remember = subcommands.add_parser("remember", help="Store a memory")
    remember.add_argument("content")
    remember.add_argument("--tenant-id", required=True)
    remember.add_argument("--type", default="OBSERVATION", choices=[item.value for item in MemoryType])
    remember.add_argument("--scope", default="PRIVATE", choices=[item.value for item in MemoryScope])
    remember.add_argument("--importance", type=float, default=0.5)
    remember.add_argument("--confidence", type=float, default=1.0)
    remember.add_argument("--no-process", action="store_true")

    recall = subcommands.add_parser("recall", help="Recall memories for a query")
    recall.add_argument("query")
    recall.add_argument("--tenant-id", required=True)
    recall.add_argument("--limit", type=int, default=10)

    context = subcommands.add_parser("context", help="Compile token-budgeted context")
    context.add_argument("query")
    context.add_argument("--tenant-id", required=True)
    context.add_argument("--token-budget", type=int, default=300)

    scheduler = subcommands.add_parser("scheduler-run", help="Run lifecycle scheduler")
    scheduler.add_argument("--tenant-id", required=True)

    args = parser.parse_args(argv)
    if args.command in (None, "serve"):
        from .api import main as serve

        serve()
        return

    amos = build_amos()
    if args.command == "health":
        _print(amos.health())
    elif args.command == "assess":
        _print(
            amos.assess_memory(
                content=args.content,
                type=MemoryType(args.type),
                importance=args.importance,
                confidence=args.confidence,
            )
        )
    elif args.command == "remember":
        _print(
            amos.remember(
                tenant_id=args.tenant_id,
                content=args.content,
                type=MemoryType(args.type),
                scope=MemoryScope(args.scope),
                importance=args.importance,
                confidence=args.confidence,
                auto_process=not args.no_process,
            )
        )
    elif args.command == "recall":
        _print(amos.recall(tenant_id=args.tenant_id, query=args.query, limit=args.limit))
    elif args.command == "context":
        _print(amos.get_context(tenant_id=args.tenant_id, query=args.query, token_budget=args.token_budget))
    elif args.command == "scheduler-run":
        _print(amos.run_scheduler(tenant_id=args.tenant_id))
    else:
        parser.error(f"unknown command: {args.command}")


def _print(value: Any) -> None:
    print(json.dumps(to_dict(value), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
