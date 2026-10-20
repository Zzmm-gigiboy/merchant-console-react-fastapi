# Merchant Console — React and FastAPI

A small inventory dashboard with React, TypeScript and a FastAPI/SQLite backend. It supports product CRUD, form validation, filtering, and discount preview. This is a demo implementation, not a live Shopify integration.

## Run

**Backend** (Python 3.11+):

```bash
cd api
python -m pip install -r requirements.txt
python -m uvicorn app:app --reload --port 8000
```

**Frontend** (Node 20+, separate terminal):

```bash
cd web
npm install
npm run dev
```

Open the Vite URL shown in the terminal (default http://localhost:5173). Open http://localhost:8000/docs for API documentation. To point the web client elsewhere, use `VITE_API_URL`.

**Tests:** `cd api && python -m pip install pytest httpx && pytest -q`.

## Scope

Local demonstration only: uses SQLite and has no authentication or production-rate limiting. Do not expose this API publicly without hardening it.
