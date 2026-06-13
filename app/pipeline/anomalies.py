from statistics import median

DOMESTIC_MERCHANTS = {"SWIGGY", "OLA", "IRCTC"}


def detect_anomalies(rows: list[dict]) -> list[dict]:
    acc_amounts: dict[str, list[float]] = {}
    for r in rows:
        acc = r.get("account_id", "")
        amt = r.get("amount", 0.0)
        if amt is not None:
            acc_amounts.setdefault(acc, []).append(amt)

    acc_medians = {acc: median(vals) for acc, vals in acc_amounts.items()}

    for r in rows:
        reasons = []
        acc = r.get("account_id", "")
        amt = r.get("amount", 0.0) or 0.0
        med = acc_medians.get(acc, 0.0)
        if med > 0 and amt > 3 * med:
            reasons.append(f"Amount {amt:.2f} exceeds 3x account median {med:.2f}")

        currency = r.get("currency", "").upper()
        merchant = r.get("merchant", "").upper()
        if currency == "USD" and merchant in DOMESTIC_MERCHANTS:
            reasons.append(f"USD transaction with domestic merchant {r.get('merchant', '')}")

        if reasons:
            r["is_anomaly"] = True
            r["anomaly_reason"] = "; ".join(reasons)
        else:
            r["is_anomaly"] = False
            r["anomaly_reason"] = None

    return rows
