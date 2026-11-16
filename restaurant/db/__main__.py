"""CLI: python -m restaurant.db migrate | status."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from restaurant.app.settings import load_settings
from restaurant.db.connection import connect
from restaurant.db.migrations import MigrationError, migrate, status


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m restaurant.db")
    parser.add_argument("command", choices=["migrate", "status"])
    parser.add_argument("--db", help="database path (default: RESTAURANT_DB_PATH)")
    args = parser.parse_args(argv)

    db_path = args.db or load_settings().db_path
    conn = connect(db_path)
    try:
        if args.command == "migrate":
            applied = migrate(conn)
            if applied:
                for name in applied:
                    print(f"applied {name}")
            else:
                print("nothing to apply; database is up to date")
        else:
            info = status(conn)
            print(f"current version: {info['current_version']}")
            for name in info["applied"]:
                print(f"  applied  {name}")
            for name in info["pending"]:
                print(f"  pending  {name}")
            for name in info["mismatched"]:
                print(f"  CHECKSUM MISMATCH  {name}")
            if info["mismatched"]:
                return 1
    except MigrationError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
