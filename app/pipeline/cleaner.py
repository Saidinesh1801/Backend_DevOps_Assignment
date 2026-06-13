import csv
import io
import re
from datetime import datetime

CLEAN_CATEGORIES = {
    "Food", "Shopping", "Travel", "Transport",
    "Utilities", "Cash Withdrawal", "Entertainment", "Other"
}


def parse_date(raw: str) -> str:
    if not raw or not raw.strip():
        return ""
    raw = raw.strip()
    for fmt in ("%d-%m-%Y", "%Y/%m/%d", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return raw


def clean_amount(raw: str) -> float:
    if not raw:
        return 0.0
    cleaned = raw.strip().replace("$", "").replace(",", "").replace(" ", "")
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


def clean_csv(file_content: str) -> list[dict]:
    reader = csv.DictReader(io.StringIO(file_content))
    rows = []
    for row in reader:
        row["date"] = parse_date(row.get("date", ""))
        row["amount"] = clean_amount(row.get("amount", "0"))
        row["currency"] = row.get("currency", "").strip().upper()
        row["status"] = row.get("status", "").strip().upper()
        raw_cat = row.get("category", "").strip()
        row["category"] = raw_cat if raw_cat else "Uncategorised"
        row["txn_id"] = row.get("txn_id", "").strip()
        row["merchant"] = row.get("merchant", "").strip()
        row["account_id"] = row.get("account_id", "").strip()
        row["notes"] = row.get("notes", "").strip()
        rows.append(row)

    seen = set()
    unique_rows = []
    for r in rows:
        key = (r["txn_id"], r["date"], r["merchant"], r["amount"], r["currency"], r["account_id"])
        if key not in seen:
            seen.add(key)
            unique_rows.append(r)

    return unique_rows
