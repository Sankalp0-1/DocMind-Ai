# DocMind AI — Document & Multimedia Q&A

> Upload PDFs, audio, and video files. Chat with your content using Groq LLM. Get summaries, jump to timestamps, and stream answers in real time.

🚀 **Live Demo:** [https://doc-mind-ai-rho.vercel.app](https://doc-mind-ai-rho.vercel.app)

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  Browser  →  React + Zustand + TailwindCSS (Vercel)             │
├─────────────────────────────────────────────────────────────────┤
│  Nginx (port 80)  — serves SPA + proxies /api → FastAPI         │
├───────────────────────────┬─────────────────────────────────────┤
│  FastAPI (Python 3.12)    │  Services                           │
│  • /api/auth              │  • FileProcessingService            │
│  • /api/upload            │    - PyMuPDF (PDF extraction)       │
│  • /api/chat  (+ SSE)     │    - OpenAI Whisper (transcription) │
│  • /api/summary           │  • VectorService (FAISS)            │
│                           │  • ChatService (RAG + streaming)    │
│                           │  • SummaryService                   │
├───────────────────────────┴─────────────────────────────────────┤
│  PostgreSQL  │  MongoDB  │  Redis                                │
│  (users,     │  (chunks, │  (cache, rate-limiting)              │
│  documents)  │  segments)│                                      │
└─────────────────────────────────────────────────────────────────┘
```

---

## Features

| Feature | Detail |
|---|---|
| File upload | PDF, MP3, WAV, OGG, MP4, WebM, MOV (up to 500 MB) |
| PDF processing | PyMuPDF — text + page numbers |
| Audio/Video | OpenAI Whisper — transcript + timestamps |
| RAG chat | FAISS semantic search → Groq LLM grounded answers |
| Streaming | SSE real-time token streaming |
| Summary | Auto-generated summary + key topics |
| Timestamps | Jump to relevant audio/video segment |
| Auth | JWT (bcrypt passwords, 24-hour tokens) |
| Rate limiting | Redis sliding-window (100 req / 60 s per IP) |
| Caching | Redis — chat answers (10 min), summaries (1 hr) |
| Testing | pytest-asyncio, 95%+ coverage |
| CI/CD | GitHub Actions — test → build → push to GHCR |
| Docker | Multi-stage builds, Docker Compose orchestration |

---

## Quick Start

### Prerequisites
- Docker & Docker Compose
- A [Groq API key](https://console.groq.com/keys)

### 1. Clone & configure

```bash
git clone https://github.com/Sankalp0-1/DocMind-Ai.git
cd DocMind-Ai

cp backend/.env.example backend/.env
# Edit backend/.env and set GROQ_API_KEY=gsk_...
```

### 2. Start everything

```bash
docker compose up --build
```

App is now live at **http://localhost**

---

## Local Development (without Docker)

### Backend

```bash
cd backend

# Create venv
python -m venv .venv && source .venv/bin/activate

# Install deps
pip install -r requirements.txt

# Copy and edit env
cp .env.example .env

# Run (needs local Postgres, Mongo, Redis)
uvicorn app.main:app --reload --port 8000
```

API docs available at http://localhost:8000/docs

### Frontend

```bash
cd frontend
npm install
npm run dev        # starts at http://localhost:3000
```

---

## Running Tests

```bash
cd backend

# All tests with coverage report
pytest

# Watch mode
pytest --watch

# Coverage only
pytest --cov=app --cov-report=term-missing
```

Coverage report is written to `backend/htmlcov/index.html`.

The CI gate requires **≥ 95% coverage** (`--cov-fail-under=95` in pytest.ini).

---

## API Reference

### Auth

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/auth/register` | Create account |
| POST | `/api/auth/token` | Login — returns JWT |
| GET | `/api/auth/me` | Current user |

### Upload

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/upload/` | Upload file (multipart/form-data) |
| GET | `/api/upload/` | List your documents |
| GET | `/api/upload/{id}` | Document detail + status |
| DELETE | `/api/upload/{id}` | Delete document |

### Chat

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/chat/` | Ask a question (`stream: true` for SSE) |
| GET | `/api/chat/{doc_id}/timestamps` | Topic timestamps (audio/video) |

### Summary

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/summary/{doc_id}` | Document summary + key topics |

All endpoints require `Authorization: Bearer <token>` except `/api/auth/register` and `/api/auth/token`.

---

## Streaming (SSE)

POST `/api/chat/` with `"stream": true` returns `text/event-stream`.

Events:
```
data: {"token": "partial answer text"}
data: {"token": " continues..."}
data: {"meta": {"sources": [...], "timestamp_hint": 42.5}}
data: [DONE]
```

---

## Environment Variables

See `backend/.env.example` for the full list. Key variables:

| Variable | Required | Default |
|---|---|---|
| `GROQ_API_KEY` | ✅ | — |
| `GROQ_CHAT_MODEL` | | `llama3-8b-8192` |
| `SECRET_KEY` | ✅ | — |
| `DATABASE_URL` | ✅ | set by compose |
| `MONGODB_URL` | ✅ | set by compose |
| `REDIS_URL` | ✅ | set by compose |
| `DEBUG` | | `false` |
| `UPLOAD_DIR` | | `uploads/` |
| `MAX_FILE_SIZE_MB` | | `500` |
| `FAISS_INDEX_PATH` | | `faiss_index/` |
| `VECTOR_DIM` | | `1536` |
| `JWT_ALGORITHM` | | `HS256` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | | `1440` |
| `RATE_LIMIT_REQUESTS` | | `100` |
| `RATE_LIMIT_WINDOW_SECONDS` | | `60` |
| `ALLOWED_ORIGINS` | | `*` |

---

## Deployment

This project is deployed using:

- **Backend** — [Railway](https://railway.app) (FastAPI + PostgreSQL + MongoDB)
- **Frontend** — [Vercel](https://vercel.com) (React SPA)

### Deploy to Railway (Backend)

1. Create a new Railway project and add your GitHub repo
2. Add **PostgreSQL** and **MongoDB** plugins — Railway auto-injects `DATABASE_URL` and `MONGODB_URL`
3. Add a **Redis** plugin or use an external Redis URL
4. Set the following environment variables in Railway → Variables:

```env
GROQ_API_KEY=gsk_...
GROQ_CHAT_MODEL=llama3-8b-8192
SECRET_KEY=your-secret-key
DEBUG=false
UPLOAD_DIR=uploads/
MAX_FILE_SIZE_MB=500
FAISS_INDEX_PATH=faiss_index/
VECTOR_DIM=1536
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=1440
RATE_LIMIT_REQUESTS=100
RATE_LIMIT_WINDOW_SECONDS=60
ALLOWED_ORIGINS=https://your-vercel-app.vercel.app
```

### Deploy to Vercel (Frontend)

1. Import the repo on [Vercel](https://vercel.com)
2. Set root directory to `frontend`
3. Add environment variable: `VITE_API_URL=https://your-railway-backend.up.railway.app`
4. Deploy

---

## CI/CD Pipeline

`.github/workflows/ci.yml` runs on every push:

1. **backend-test** — pytest with 95% coverage gate
2. **frontend-test** — vitest + build check
3. **docker-push** *(main only)* — builds & pushes images to GHCR

To enable deploy, uncomment the `deploy` job and set:
- `DEPLOY_HOST`, `DEPLOY_USER`, `DEPLOY_KEY` secrets in GitHub

---

## Project Structure

```
DocMind-Ai/
├── backend/
│   ├── app/
│   │   ├── api/          # Route handlers (auth, upload, chat, summary)
│   │   ├── core/         # Config, DB, security, Redis, logger
│   │   ├── models/       # SQLAlchemy models + Pydantic schemas
│   │   ├── services/     # Business logic (file processing, chat, vector, summary)
│   │   └── tests/        # pytest test suite
│   ├── Dockerfile
│   ├── requirements.txt
│   └── pytest.ini
├── frontend/
│   ├── src/
│   │   ├── components/   # Layout
│   │   ├── pages/        # Login, Register, Dashboard, Chat
│   │   ├── store/        # Zustand auth + doc stores
│   │   └── utils/        # Axios client, formatters
│   ├── Dockerfile
│   └── nginx.conf
├── docker-compose.yml
└── .github/workflows/ci.yml
```

---

## License

MIT