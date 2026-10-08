"""Minimal fixed-scope integrity/coverage check for a public GitHub Parquet archive.

Runs only in a manual/branch GitHub Actions audit. It does NOT collect live prices,
backtest, calibrate probabilities, or alter the current options observer.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import urllib.request

import duckdb

DATA_REPO = "anahatsingh-ui/options-dataset-hist"
DATA_COMMIT = "37f6c456fe1a4775c875673fb8ef907d5cd2fd66"
FILES = {
    "spy/options_2024.parquet": (56_948_550, "8e0b7ca48dffa92fe93ceeffefdfce8557eab74a"),
    "spy/underlying_prices.parquet": (252_066, "4c22934a77ba09ced10fd1c413b5d8c9e0cb4a8d"),
}
REQUIRED = {
    "contract_id", "symbol", "expiration", "strike", "type", "bid", "ask",
    "date", "implied_volatility", "delta", "open_interest", "volume",
}


def fetch_verified(path: str, target: Path) -> None:
    size, git_blob_sha = FILES[path]
    url = f"https://raw.githubusercontent.com/{DATA_REPO}/{DATA_COMMIT}/{path}"
    request = urllib.request.Request(url, headers={"User-Agent": "SiftAlpha-personal-research"})
    with urllib.request.urlopen(request, timeout=120) as src, target.open("wb") as dst:
        while data := src.read(1024 * 1024):
            dst.write(data)
            if dst.tell() > size:
                raise ValueError("File larger than pinned upstream GitHub blob size")
    content = target.read_bytes()
    actual_git_blob_sha = hashlib.sha1(
        f"blob {len(content)}\0".encode() + content
    ).hexdigest()
    if len(content) != size or actual_git_blob_sha != git_blob_sha:
        raise ValueError(f"GitHub data blob mismatch for {path}")
    print(json.dumps({"download": path, "bytes": size, "git_blob_sha_verified": True}), flush=True)


def run() -> None:
    with tempfile.TemporaryDirectory(prefix="siftalpha-options-pilot-") as temp:
        root = Path(temp)
        opt = root / "options_2024.parquet"
        px = root / "underlying_prices.parquet"
        fetch_verified("spy/options_2024.parquet", opt)
        fetch_verified("spy/underlying_prices.parquet", px)
        db = duckdb.connect(":memory:")
        # No data mutation or publication; DuckDB can scan Parquet in place.
        opt_schema = set(
            row[0] for row in db.execute("DESCRIBE SELECT * FROM read_parquet(?)", [str(opt)]).fetchall()
        )
        missing = REQUIRED - opt_schema
        if missing:
            raise AssertionError(f"Missing required option columns: {sorted(missing)}")
        px_schema = set(
            row[0] for row in db.execute("DESCRIBE SELECT * FROM read_parquet(?)", [str(px)]).fetchall()
        )
        missing_px = {"date", "close"} - px_schema
        if missing_px:
            raise AssertionError(f"Missing required underlying columns: {sorted(missing_px)}")
        db.execute(f"CREATE VIEW o AS SELECT * FROM read_parquet('{opt.as_posix()}')")
        db.execute(f"CREATE VIEW u AS SELECT * FROM read_parquet('{px.as_posix()}')")
        summary = db.execute("""
            SELECT
                COUNT(*) AS rows,
                COUNT(DISTINCT "date") AS trading_dates,
                CAST(MIN("date") AS VARCHAR) AS first_date,
                CAST(MAX("date") AS VARCHAR) AS last_date,
                COUNT(*) FILTER (WHERE LOWER(CAST("type" AS VARCHAR)) IN ('call', 'c')) AS call_rows,
                COUNT(*) FILTER (WHERE LOWER(CAST("type" AS VARCHAR)) IN ('put', 'p')) AS put_rows,
                COUNT(*) FILTER (WHERE bid IS NULL OR ask IS NULL OR bid <= 0 OR ask < bid) AS bad_quote_rows,
                COUNT(*) FILTER (WHERE implied_volatility IS NULL OR NOT isfinite(implied_volatility) OR implied_volatility <= 0) AS bad_iv_rows,
                COUNT(*) FILTER (WHERE delta IS NULL OR NOT isfinite(delta)) AS missing_or_invalid_delta_rows,
                COUNT(*) FILTER (WHERE strike IS NULL OR strike <= 0) AS bad_strike_rows,
                COUNT(*) FILTER (WHERE "date" IS NULL OR expiration IS NULL OR expiration < "date") AS bad_date_rows,
                COUNT(*) FILTER (WHERE contract_id IS NULL OR CAST(contract_id AS VARCHAR) = '') AS missing_contract_id_rows
            FROM o
        """).fetchone()
        cols = [
            "rows", "trading_dates", "first_date", "last_date", "call_rows", "put_rows",
            "bad_quote_rows", "bad_iv_rows", "missing_or_invalid_delta_rows",
            "bad_strike_rows", "bad_date_rows", "missing_contract_id_rows",
        ]
        result = dict(zip(cols, summary))
        result["underlying_days"] = db.execute(
            "SELECT COUNT(DISTINCT \"date\") FROM u WHERE close > 0"
        ).fetchone()[0]
        result["missing_underlying_close_for_option_rows"] = db.execute("""
            SELECT COUNT(*)
              FROM o LEFT JOIN u ON o."date" = u."date"
             WHERE u.close IS NULL OR u.close <= 0
        """).fetchone()[0]
        result["sample_contract"] = db.execute("""
            SELECT CAST("date" AS VARCHAR), CAST(expiration AS VARCHAR),
                   CAST("type" AS VARCHAR), CAST(strike AS DOUBLE),
                   CAST(bid AS DOUBLE), CAST(ask AS DOUBLE),
                   CAST(implied_volatility AS DOUBLE)
              FROM o
             WHERE bid > 0 AND ask >= bid AND implied_volatility > 0
             ORDER BY "date" DESC, contract_id LIMIT 1
        """).fetchone()
        result["has_intraday_option_quote_timestamp"] = any(
            k in opt_schema for k in ("quote_timestamp", "quote_time", "quoted_at")
        )
        result["validation_scope"] = "SPY 2024 only; genuine matching byte blobs; content does NOT establish exchange provenance"
        print("DATASET_AUDIT_JSON=" + json.dumps(result, ensure_ascii=False, default=str), flush=True)
        if result["rows"] < 500 or not result["call_rows"] or not result["put_rows"]:
            raise AssertionError("Historical contract data empty or incomplete")
        if result["missing_underlying_close_for_option_rows"] >= result["rows"]:
            raise AssertionError("No corresponding underlying stock closes")
        print("DATASET_STRUCTURAL_AUDIT_PASS", flush=True)
        print("HISTORICAL_PROBABILITY_CALIBRATION_NOT_PERFORMED", flush=True)
        print("EXACT_QUOTE_TIMESTAMP_NOT_VERIFIED", flush=True)


if __name__ == "__main__":
    run()
