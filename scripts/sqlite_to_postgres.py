#!/usr/bin/env python3
"""
SQLite -> PostgreSQL migration entrypoint (skeleton).

Usage:
  python scripts/sqlite_to_postgres.py \
      --source var/db/quant_trader.db \
      --target postgresql+psycopg://user:pass@host:5432/quant_trader
"""
from __future__ import annotations

import argparse


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="SQLite to PostgreSQL migration skeleton")
    parser.add_argument("--source", required=True, help="Source sqlite file path")
    parser.add_argument("--target", required=True, help="Target PostgreSQL SQLAlchemy URL")
    parser.add_argument("--dry-run", action="store_true", help="Validate connectivity and table mapping only")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    print("[migration] source:", args.source)
    print("[migration] target:", args.target)
    if args.dry_run:
        print("[migration] dry-run enabled, no write operations executed.")
    else:
        print("[migration] not implemented yet. This scaffold is reserved for phase-2 PG migration.")


if __name__ == "__main__":
    main()
