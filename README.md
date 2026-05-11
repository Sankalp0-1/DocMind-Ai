# DocMind AI — Document & Multimedia Q&A

> Upload PDFs, audio, and video files. Chat with your content using GPT-4o. Get summaries, jump to timestamps, and stream answers in real time.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  Browser  →  React + Zustand + TailwindCSS                       │
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
| RAG chat | FAISS semantic search → GPT-4o grounded answers |
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
- An [OpenAI API key](https://platform.openai.com/api-keys)

### 1. Clone & configure

```bash
git clone https://github.com/your-org/ai-qa-app.git
cd ai-qa-app

cp backend/.env.example backend/.env
# Edit backend/.env and set OPENAI_API_KEY=sk-...
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
| `OPENAI_API_KEY` | ✅ | — |
| `SECRET_KEY` | ✅ | — |
| `DATABASE_URL` | ✅ | set by compose |
| `MONGODB_URL` | ✅ | set by compose |
| `REDIS_URL` | ✅ | set by compose |
| `OPENAI_CHAT_MODEL` | | `gpt-4o` |
| `MAX_FILE_SIZE_MB` | | `500` |

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
ai-qa-app/
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
