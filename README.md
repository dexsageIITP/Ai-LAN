# Ai-LAN

Ai-LAN is an independent civic reporting platform for mapping, routing, and tracking public infrastructure issues. It can run in live site mode with Gemini analysis, authenticated users, and backend-managed uploads. Demonstration records remain explicitly labelled until replaced with verified authority data.

## Run locally

### Backend

```bash
cd backend
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

The backend uses SQLite for local development and private local uploads. Copy `.env.example` to `.env` and set a valid `GEMINI_API_KEY` before enabling live AI analysis. `DEMO_MODE=false` enables live-site status reporting. The current API includes registration and login endpoints at `/api/auth/register` and `/api/auth/login`. If `GEMINI_API_KEY` is empty, reports are retained and explicitly marked `not_configured` for manual review.

For deployment, set `DATABASE_URL` to a managed PostgreSQL connection and migrate the persistence adapter before exposing the service publicly. The local MVP schema is intentionally SQLite-compatible.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`. Set `VITE_API_URL` if the API is hosted elsewhere.

## Included MVP flows

- Overview metrics calculated from stored reports
- Civic map-style view with severity markers, category filtering, search, and report details
- Photograph and coordinate validation on report submission
- Gemini multimodal classification with schema validation and manual-review fallback
- PBKDF2 password hashing and registration/login endpoints
- Authority directory with verified/demo contact labels
- Complaint history and status updates
- Category and severity analytics
- `/api/health` configuration and database status

All external provider credentials belong in backend environment variables and are never bundled into the frontend.
