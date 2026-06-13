# AI-Powered Transaction Processing Pipeline

Backend API that accepts dirty CSV transaction data, processes it asynchronously with LLM-powered classification and anomaly detection, and returns structured reports.

## Quick Start

```bash
docker compose up --build
```

All services start automatically. API available at `http://localhost:8000`.

## API Endpoints

```bash
# 1. Upload CSV
curl -X POST http://localhost:8000/jobs/upload \
  -F "file=@transactions.csv"

# 2. Check job status
curl http://localhost:8000/jobs/{job_id}/status

# 3. Get full results
curl http://localhost:8000/jobs/{job_id}/results

# 4. List all jobs
curl http://localhost:8000/jobs
curl "http://localhost:8000/jobs?status=completed"
```

## Architecture

```
┌──────────┐    POST /upload     ┌──────────┐    enqueue    ┌──────────┐
│  Client   │ ──────────────────> │  FastAPI  │ ───────────> │  RQ +    │
│  (curl)   │ <────────────────── │  (api)    │              │  Redis   │
└──────────┘    JSON responses    └──────────┘              └────┬─────┘
                                                                 │
                                                    ┌────────────┴────────────┐
                                                    │     RQ Worker            │
                                                    │  1. Clean CSV            │
                                                    │  2. Detect anomalies     │
                                                    │  3. LLM classify         │
                                                    │  4. Generate summary     │
                                                    │  5. Store in PostgreSQL  │
                                                    └─────────────────────────┘
```

## Tech Stack

| Component     | Technology         |
|---------------|--------------------|
| API           | FastAPI            |
| Database      | PostgreSQL 16      |
| Job Queue     | RQ + Redis         |
| LLM           | Mock / Gemini / OpenAI / Ollama |
| Container     | Docker Compose     |

## LLM Configuration

Set `LLM_PROVIDER` and corresponding key in `docker-compose.yml`:

| Provider | Env Variables                                  |
|----------|------------------------------------------------|
| mock     | `LLM_PROVIDER=mock` (default, no key needed)   |
| gemini   | `LLM_PROVIDER=gemini` + `GEMINI_API_KEY=...`   |
| openai   | `LLM_PROVIDER=openai` + `OPENAI_API_KEY=...`   |
| ollama   | `LLM_PROVIDER=ollama` + `OLLAMA_BASE_URL=...`  |

## Processing Pipeline

1. **Clean** — Normalize dates, remove `$` from amounts, uppercase currency/status, fill blank categories, remove duplicates
2. **Anomaly Detection** — Flag statistical outliers (>3× account median) and USD+domestic-merchant combos
3. **LLM Classification** — Batch categorize uncategorized transactions into Food/Shopping/Travel/Transport/Utilities/Cash Withdrawal/Entertainment/Other
4. **LLM Summary** — Single call to generate spend totals, top merchants, narrative, risk level
5. **Retry** — Failed LLM calls retry 3× with exponential backoff; job continues on failure

## Example Workflow

```bash
# Upload
JOB_ID=$(curl -s -X POST http://localhost:8000/jobs/upload \
  -F "file=@transactions.csv" | python -c "import sys,json;print(json.load(sys.stdin)['job_id'])")

# Poll until done
while true; do
  status=$(curl -s http://localhost:8000/jobs/$JOB_ID/status | python -c "import sys,json;print(json.load(sys.stdin)['status'])")
  echo "Status: $status"
  [ "$status" = "completed" ] || [ "$status" = "failed" ] && break
  sleep 2
done

# Get results
curl -s http://localhost:8000/jobs/$JOB_ID/results | python -m json.tool
```
