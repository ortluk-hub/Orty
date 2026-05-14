#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import re
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SCHEMA = ROOT / 'service' / 'storage' / 'postgres_schema_phase1.sql'
REQUIRED_TABLES = ('clients', 'client_access_tokens', 'messages', 'memory_records', 'memory_summaries', 'bug_reports')


def normalize_schema(sql: str) -> str:
    sql = re.sub(r'^\s*BEGIN;\s*', '', sql, flags=re.MULTILINE)
    sql = re.sub(r'\s*COMMIT;\s*$', '\n', sql, flags=re.MULTILINE)
    return sql.strip() + '\n'


def main() -> int:
    parser = argparse.ArgumentParser(description='Apply Orty PostgreSQL phase 1 schema.')
    parser.add_argument('--database-url', default=os.getenv('DATABASE_URL'), help='PostgreSQL connection string')
    parser.add_argument('--schema', default=str(DEFAULT_SCHEMA), help='Path to schema SQL file')
    parser.add_argument('--check-only', action='store_true', help='Validate required tables without applying schema')
    args = parser.parse_args()

    if not args.database_url:
        raise SystemExit('DATABASE_URL is required via --database-url or environment')

    schema_path = Path(args.schema).resolve()
    if not schema_path.exists():
        raise SystemExit(f'Schema file not found: {schema_path}')

    schema_sql = normalize_schema(schema_path.read_text(encoding='utf-8'))

    with psycopg.connect(args.database_url) as conn:
        if not args.check_only:
            with conn.cursor() as cur:
                cur.execute(schema_sql)
            conn.commit()

        with conn.cursor() as cur:
            cur.execute(
                'SELECT tablename FROM pg_tables WHERE schemaname = current_schema() AND tablename = ANY(%s)',
                (list(REQUIRED_TABLES),),
            )
            existing = {row[0] for row in cur.fetchall()}

    missing = [name for name in REQUIRED_TABLES if name not in existing]
    if missing:
        raise SystemExit(f'Missing required tables after schema check: {", ".join(missing)}')

    action = 'validated' if args.check_only else 'applied and validated'
    print(f'Orty PostgreSQL schema {action}: {schema_path}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
