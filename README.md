# Pantheon

Open-source AI council platform: a FastAPI + LangGraph backend and a React (Vite) frontend.

## Structure

- `backend/` — FastAPI app (`app/main:app`), SQLAlchemy models, LangGraph deliberation workflow.
- `frontend/` — React SPA (Vite).

## Quick start

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
.venv/bin/python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

### Frontend

```bash
cd frontend
npm install
cp .env.example .env
npm run dev
```

## License

MIT
