# Setup guide

## Prerequisites

- Python 3.11+ (developed on 3.13) and Node 20+ (developed on 22)
- Optional: [Ollama](https://ollama.com) for a real local model

## 1. Backend

```bash
cd backend
python -m venv ../.venv
source ../.venv/bin/activate          # Windows PowerShell: ..\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
cp .env.example .env                  # Windows: copy .env.example .env
uvicorn app.main:app_factory --factory --reload
```

Check: open http://127.0.0.1:8000/docs, or `curl http://127.0.0.1:8000/api/health`.

## 2. Local model (recommended)

```bash
ollama serve
ollama pull llama3.2
```

Settings → *Language model* shows `reachable` / `model available`. Without Ollama the app still runs: answers come from the labelled offline fallback.

To use an OpenAI-compatible API instead, set in `backend/.env`:

```
LLM_PROVIDER=openai
OPENAI_API_KEY=...
OPENAI_MODEL=gpt-4o-mini
```

To run without any model: `LLM_PROVIDER=offline`.

## 3. Frontend

```bash
cd frontend
npm install
npm run dev                            # http://localhost:5173
```

The dev server proxies `/api` to `127.0.0.1:8000`. For a different backend URL set `VITE_API_URL` at build time.

Production build: `npm run build` (output in `frontend/dist`, serve with any static server, and add its origin to `CORS_ORIGINS`).

## 4. Tests

```bash
cd backend && pytest && ruff check .
cd frontend && npm run typecheck && npm run lint && npm test && npm run build
python scripts/e2e_demo.py             # needs the backend dependencies; starts its own server on a free port
```

`E2E_PROVIDER=ollama python scripts/e2e_demo.py` runs the same script against a real model (assertions on wording are written loosely, but model behaviour can still vary).

The live Ollama test in `backend/tests/test_providers.py` runs automatically when Ollama is reachable with the configured model and is skipped otherwise.

## 5. Data and reset

Databases live in `backend/data/` (`checkpoints.db`, `memory_store.db`, `app.db`). Stop the server and delete the folder to reset everything, or use Settings → *Delete all my data* for one user.

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| Chips say `offline` on answers | Primary model unreachable. Start `ollama serve`, `ollama pull <model>`, then Settings → Refresh |
| Token counter shows `approx:chars/4` | tiktoken could not load its vocabulary (needs a one-time download). Connect once, or accept the labelled estimate |
| Browser shows CORS errors | Add the frontend origin to `CORS_ORIGINS` |
| `Address already in use` | Use `--port 8001` and set `VITE_API_URL` / the vite proxy accordingly |
