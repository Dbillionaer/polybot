"""Audit or repair legacy PolyBot position rows using corrected trade replay semantics."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
import sys

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.database import (
    create_db_and_tables,
    get_all_positions,
    get_all_trades,
    repair_legacy_positions_from_trades,
)

GAMMA_API_URL = "https://gamma-api.polymarket.com"


def load_market_metadata(markets_file: str | None) -> dict[str, dict[str, str]]:
    metadata: dict[str, dict[str, str]] = {}
    if markets_file and Path(markets_file).exists():
        with open(markets_file, encoding="utf-8") as handle:
            for market in json.load(handle):
                token_id = str(market.get("token_id") or market.get("tokenId") or "")
                if not token_id:
                    continue
                metadata[token_id] = {
                    "token_id": token_id,
                    "condition_id": str(market.get("condition_id") or market.get("conditionId") or token_id),
                    "outcome": str(market.get("outcome")) if market.get("outcome") else "",
                }
    return metadata


def fetch_missing_gamma_metadata(token_ids: set[str], metadata: dict[str, dict[str, str]]) -> None:
    session = requests.Session()
    for token_id in sorted(token_ids):
        if token_id in metadata:
            continue
        try:
            response = session.get(
                f"{GAMMA_API_URL}/markets",
                params={"clob_token_ids": token_id},
                timeout=8,
            )
            response.raise_for_status()
            payload = response.json()
            market = payload[0] if isinstance(payload, list) and payload else payload
            if not isinstance(market, dict):
                continue
            tokens = market.get("clobTokenIds") or market.get("tokens") or []
            if isinstance(tokens, str):
                try:
                    tokens = json.loads(tokens)
                except json.JSONDecodeError:
                    tokens = []
            outcome = ""
            for token in tokens:
                if isinstance(token, dict):
                    candidate = str(
                        token.get("token_id")
                        or token.get("tokenId")
                        or token.get("clobTokenId")
                        or token.get("id")
                        or ""
                    )
                    if candidate == token_id:
                        outcome = str(token.get("outcome") or token.get("name") or token.get("label") or "")
                        break
            metadata[token_id] = {
                "token_id": token_id,
                "condition_id": str(market.get("conditionId") or token_id),
                "outcome": outcome,
            }
        except Exception:
            continue


def write_backup(backup_dir: str, positions: list[dict]) -> str:
    target_dir = Path(backup_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    backup_path = target_dir / f"positions-backup-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
    with open(backup_path, "w", encoding="utf-8") as handle:
        json.dump(positions, handle, indent=2)
    return str(backup_path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Rewrite the position table if the audit is safe.")
    parser.add_argument("--markets-file", default="markets.json", help="Optional market metadata JSON file.")
    parser.add_argument("--backup-dir", default="artifacts/ledger-backups", help="Where to write position backups before apply.")
    args = parser.parse_args()

    create_db_and_tables()
    metadata = load_market_metadata(args.markets_file)
    token_ids = {position.token_id for position in get_all_positions()} | {trade.token_id for trade in get_all_trades()}
    fetch_missing_gamma_metadata(token_ids, metadata)

    audit_report = repair_legacy_positions_from_trades(metadata, apply=False)
    if args.apply:
        if not audit_report["can_apply"]:
            print(json.dumps(audit_report, indent=2))
            return 1
        backup_path = write_backup(args.backup_dir, audit_report["backup_positions"])
        applied_report = repair_legacy_positions_from_trades(metadata, apply=True)
        applied_report["backup_path"] = backup_path
        print(json.dumps(applied_report, indent=2))
        return 0 if applied_report["applied"] else 1

    print(json.dumps(audit_report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())