import json
import time
from typing import Optional

import httpx

from app.config import settings

CLASSIFICATION_SYSTEM = "You are a transaction categorizer. Assign categories from: Food, Shopping, Travel, Transport, Utilities, Cash Withdrawal, Entertainment, Other."

CLASSIFICATION_USER = """For each transaction below, respond with a JSON array of objects with "txn_id" and "category" fields.

Transactions:
{transactions}"""

SUMMARY_SYSTEM = "You are a financial analyst. Generate concise financial summaries from transaction data."

SUMMARY_USER = """Given this transaction data, return a JSON object with:
- "total_spend_inr": float
- "total_spend_usd": float
- "top_merchants": list of {"merchant": str, "count": int, "total": float}
- "anomaly_count": int
- "narrative": str (2-3 sentences)
- "risk_level": str ("low"/"medium"/"high")

Data:
{data}"""


def _retry_with_backoff(fn, max_retries: int = None, backoff: float = None):
    if max_retries is None:
        max_retries = settings.MAX_RETRIES
    if backoff is None:
        backoff = settings.RETRY_BACKOFF
    last_err = None
    for attempt in range(max_retries):
        try:
            return fn()
        except Exception as e:
            last_err = e
            if attempt < max_retries - 1:
                time.sleep(backoff ** attempt)
    raise last_err


def _call_mock(prompt_type: str, payload: str) -> str:
    if prompt_type == "classify":
        lines = [l for l in payload.strip().split("\n") if l.strip()]
        results = []
        for line in lines:
            parts = line.split(",", 1)
            txn_id = parts[0].strip()
            results.append({"txn_id": txn_id, "category": "Other"})
        return json.dumps(results)
    else:
        import re
        inr_amounts = [float(m) for m in re.findall(r'"amount":\s*([\d.]+).*?"currency":\s*"INR"', payload, re.DOTALL)]
        usd_amounts = [float(m) for m in re.findall(r'"amount":\s*([\d.]+).*?"currency":\s*"USD"', payload, re.DOTALL)]
        merchant_pattern = re.findall(r'"merchant":\s*"([^"]+)".*?"amount":\s*([\d.]+)', payload, re.DOTALL)
        merchant_totals = {}
        for m, a in merchant_pattern:
            merchant_totals[m] = merchant_totals.get(m, 0) + float(a)
        top = sorted(merchant_totals.items(), key=lambda x: -x[1])[:5]
        total_inr = sum(inr_amounts)
        total_usd = sum(usd_amounts)
        anomaly_match = re.search(r'Anomalies:\s*(\d+)', payload)
        anomaly_count = int(anomaly_match.group(1)) if anomaly_match else 0
        return json.dumps({
            "total_spend_inr": round(total_inr, 2),
            "total_spend_usd": round(total_usd, 2),
            "top_merchants": [{"merchant": m, "count": 0, "total": round(t, 2)} for m, t in top],
            "anomaly_count": anomaly_count,
            "narrative": f"Processed transactions. Total INR spend: {total_inr:,.2f}, Total USD spend: {total_usd:,.2f}.",
            "risk_level": "high" if anomaly_count > 10 else "medium" if anomaly_count > 3 else "low"
        })


def _call_gemini(system_prompt: str, user_prompt: str) -> str:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={settings.GEMINI_API_KEY}"
    body = {
        "contents": [{"parts": [{"text": f"{system_prompt}\n\n{user_prompt}"}]}]
    }
    resp = httpx.post(url, json=body, timeout=60)
    resp.raise_for_status()
    data = resp.json()
    candidates = data.get("candidates", [])
    if candidates:
        return candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
    raise ValueError("No response from Gemini")


def _call_openai(system_prompt: str, user_prompt: str) -> str:
    url = "https://api.openai.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {settings.OPENAI_API_KEY}"}
    body = {
        "model": settings.OPENAI_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "temperature": 0.1
    }
    resp = httpx.post(url, json=body, headers=headers, timeout=60)
    resp.raise_for_status()
    data = resp.json()
    return data["choices"][0]["message"]["content"]


def _call_ollama(system_prompt: str, user_prompt: str) -> str:
    url = f"{settings.OLLAMA_BASE_URL}/api/generate"
    body = {
        "model": settings.OLLAMA_MODEL,
        "prompt": f"{system_prompt}\n\n{user_prompt}",
        "stream": False
    }
    resp = httpx.post(url, json=body, timeout=120)
    resp.raise_for_status()
    data = resp.json()
    return data.get("response", "")


def _call_llm(system_prompt: str, user_prompt: str) -> str:
    provider = settings.LLM_PROVIDER
    if provider == "mock":
        return _call_mock("classify" if "categorizer" in system_prompt.lower() else "summary", user_prompt)
    elif provider == "gemini":
        return _call_gemini(system_prompt, user_prompt)
    elif provider == "openai":
        return _call_openai(system_prompt, user_prompt)
    elif provider == "ollama":
        return _call_ollama(system_prompt, user_prompt)
    else:
        raise ValueError(f"Unknown LLM provider: {provider}")


def classify_transactions(rows: list[dict]) -> list[dict]:
    needs_llm = [r for r in rows if r.get("category", "").lower() == "uncategorised"]
    if not needs_llm:
        return rows

    txn_lines = "\n".join(
        f"{r.get('txn_id', '') or '(no id)'}, merchant={r.get('merchant', '')}, "
        f"amount={r.get('amount', 0)}, notes={r.get('notes', '')}"
        for r in needs_llm
    )
    user_prompt = CLASSIFICATION_USER.replace("{transactions}", txn_lines)

    try:
        result = _retry_with_backoff(lambda: _call_llm(CLASSIFICATION_SYSTEM, user_prompt))
        parsed = _parse_classification(result, needs_llm)
        for r in needs_llm:
            txn_id = r.get("txn_id", "")
            cat = parsed.get(txn_id)
            if cat:
                r["llm_category"] = cat
                r["category"] = cat
            r["llm_raw_response"] = result
            r["llm_failed"] = cat is None
    except Exception as e:
        for r in needs_llm:
            r["llm_category"] = None
            r["llm_raw_response"] = str(e)
            r["llm_failed"] = True

    return rows


def _parse_classification(raw: str, rows: list[dict]) -> dict[str, str]:
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            return {item.get("txn_id", ""): item.get("category", "Other") for item in data}
    except json.JSONDecodeError:
        pass
    import re
    matches = re.findall(r'"txn_id"\s*:\s*"([^"]*)"\s*,\s*"category"\s*:\s*"([^"]*)"', raw)
    if matches:
        return {m[0]: m[1] for m in matches}
    return {}


def generate_summary(rows: list[dict], anomaly_count: int) -> Optional[dict]:
    sample = json.dumps([
        {"merchant": r.get("merchant"), "amount": r.get("amount"), "currency": r.get("currency"),
         "category": r.get("category"), "is_anomaly": r.get("is_anomaly", False)}
        for r in rows[:50]
    ], indent=2)
    data_str = f"Total rows: {len(rows)}, Anomalies: {anomaly_count}\nSample:\n{sample}"
    user_prompt = SUMMARY_USER.replace("{data}", data_str)

    try:
        result = _retry_with_backoff(lambda: _call_llm(SUMMARY_SYSTEM, user_prompt))
        return json.loads(result)
    except Exception:
        return None
