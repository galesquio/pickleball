#!/usr/bin/env python3
"""Deploy pickleball to Render via the public API (PostgreSQL by default).

Requires:
  set RENDER_API_KEY=rnd_...   (from CLI `render login` or dashboard API keys)

Usage:
  python scripts/deploy_render.py              # PostgreSQL (matches render.yaml)
  python scripts/deploy_render.py --sqlite     # SQLite on the web service instead
  python scripts/deploy_render.py --dry-run

Prefer deploying with `render.yaml` Blueprint from the dashboard when possible.
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import sys
import time
import urllib.error
import urllib.request

API = "https://api.render.com/v1"
REPO = "https://github.com/galesquio/pickleball"
BRANCH = "main"
WEB_NAME = "pickleball"
DB_NAME = "pickleball-db"


def api(method: str, path: str, key: str, body: dict | None = None) -> dict | list:
    url = f"{API}{path}"
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {key}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            raw = resp.read().decode()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        detail = e.read().decode()
        raise SystemExit(f"Render API {method} {path} failed ({e.code}): {detail}") from e


def first_owner_id(key: str) -> str:
    owners = api("GET", "/owners", key)
    if not owners:
        raise SystemExit("No Render workspaces found on this account.")
    item = owners[0]
    owner = item.get("owner") or item
    return owner["id"]


def wait_postgres_ready(key: str, postgres_id: str, timeout: int = 900) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        row = api("GET", f"/postgres/{postgres_id}", key)
        pg = row.get("postgres") or row
        status = (pg.get("status") or "").lower()
        if status == "available":
            return pg
        if status in ("failed", "suspended"):
            raise SystemExit(f"Postgres {postgres_id} entered status {status!r}")
        time.sleep(15)
    raise SystemExit(f"Timed out waiting for Postgres {postgres_id}")


def connection_string(key: str, postgres_id: str, pg: dict) -> str:
    info = api("GET", f"/postgres/{postgres_id}/connection-info", key)
    conn = info.get("connectionInfo") or info
    for field in (
        "internalConnectionString",
        "connectionString",
        "externalConnectionString",
    ):
        val = conn.get(field)
        if val:
            return val
    raise SystemExit("Postgres is available but no connection string was returned.")


def find_web_service(key: str) -> dict | None:
    for svc in api("GET", "/services", key) or []:
        s = svc.get("service") or svc
        if s.get("name") == WEB_NAME and s.get("type") == "web_service":
            return s
    return None


def web_env_vars_sqlite(pb_secret: str, data_dir: str | None = None) -> list[dict]:
    env = [
        {"key": "PYTHON_VERSION", "value": "3.12.7"},
        {"key": "RENDER", "value": "true"},
        {"key": "PB_SECRET_KEY", "value": pb_secret},
    ]
    if data_dir:
        env.append({"key": "DATA_DIR", "value": data_dir})
    return env


def web_service_details() -> dict:
    return {
        "runtime": "python",
        "plan": "free",
        "healthCheckPath": "/login",
        "envSpecificDetails": {
            "buildCommand": "pip install -r requirements.txt",
            "startCommand": "uvicorn app:create_app --factory --host 0.0.0.0 --port $PORT",
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Deploy pickleball to Render")
    parser.add_argument("--dry-run", action="store_true", help="Print planned actions only")
    parser.add_argument(
        "--sqlite",
        action="store_true",
        help="Use SQLite on the web service instead of Render PostgreSQL",
    )
    parser.add_argument(
        "--data-dir",
        default="",
        help="DATA_DIR for SQLite file (e.g. /var/data with a persistent disk)",
    )
    args = parser.parse_args()

    key = os.environ.get("RENDER_API_KEY", "").strip()
    if not key:
        raise SystemExit(
            "Set RENDER_API_KEY (create one at "
            "https://dashboard.render.com/u/settings#api-keys)"
        )

    owner_id = first_owner_id(key)
    pb_secret = secrets.token_urlsafe(32)
    data_dir = args.data_dir.strip() or None

    env_vars = web_env_vars_sqlite(pb_secret, data_dir)

    plan = {
        "mode": "sqlite" if args.sqlite else "postgres",
        "owner_id": owner_id,
        "data_dir": data_dir,
        "web": {
            "envVars": env_vars,
            "serviceDetails": web_service_details(),
        },
    }

    if args.dry_run:
        print(json.dumps(plan, indent=2))
        return

    existing_web = find_web_service(key)

    if not args.sqlite:
        existing_pg = None
        for row in api("GET", "/postgres", key) or []:
            pg = row.get("postgres") or row
            if pg.get("name") == DB_NAME:
                existing_pg = pg
                break
        if existing_pg:
            pg_id = existing_pg["id"]
            print(f"Using existing Postgres: {DB_NAME} ({pg_id})")
            pg = wait_postgres_ready(key, pg_id, timeout=60)
        else:
            print(f"Creating Postgres: {DB_NAME} ...")
            created = api(
                "POST",
                "/postgres",
                key,
                {
                    "name": DB_NAME,
                    "ownerId": owner_id,
                    "plan": "free",
                    "version": "16",
                    "databaseName": "pickleball",
                    "databaseUser": "pickleball",
                },
            )
            pg_row = created.get("postgres") or created
            pg_id = pg_row["id"]
            pg = wait_postgres_ready(key, pg_id)
        db_url = connection_string(key, pg_id, pg)
        env_vars = [
            {"key": "PYTHON_VERSION", "value": "3.12.7"},
            {"key": "RENDER", "value": "true"},
            {"key": "PB_SECRET_KEY", "value": pb_secret},
            {"key": "DATABASE_URL", "value": db_url},
        ]
    else:
        print("Deploying with SQLite (pickleball.db on the service filesystem).")
        print("Note: on the free plan, SQLite data is reset when you redeploy.")
        print("Prefer render.yaml Blueprint with PostgreSQL for production.")

    web_body = {
        "type": "web_service",
        "name": WEB_NAME,
        "ownerId": owner_id,
        "repo": REPO,
        "branch": BRANCH,
        "autoDeploy": "yes",
        "envVars": env_vars,
        "serviceDetails": web_service_details(),
    }

    if existing_web:
        web_id = existing_web["id"]
        print(f"Updating web service: {WEB_NAME} ({web_id}) ...")
        api("PATCH", f"/services/{web_id}", key, web_body)
        api("POST", f"/services/{web_id}/deploys", key, {})
    else:
        print(f"Creating web service: {WEB_NAME} ...")
        created = api("POST", "/services", key, web_body)
        web = created.get("service") or created
        web_id = web["id"]

    for _ in range(60):
        row = api("GET", f"/services/{web_id}", key)
        svc = row.get("service") or row
        url = svc.get("serviceDetails", {}).get("url") or svc.get("url")
        if url:
            print(f"\nDeployed. Open: {url}")
            print("Default login (if DB was empty): admin / admin123 - change immediately.")
            return
        time.sleep(5)

    print(f"\nDeploy started. Service id={web_id}")
    print("Check status: https://dashboard.render.com/")


if __name__ == "__main__":
    main()
