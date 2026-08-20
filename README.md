# AetherLab

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.141-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-17-336791?logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-2.0-D71F00?logo=sqlalchemy)](https://www.sqlalchemy.org/)
[![License](https://img.shields.io/badge/License-View%20LICENSE-blue)](/LICENSE)

AetherLab is an intelligent environmental platform that combines **geospatial data, weather, air quality, satellite imagery, and autonomous systems** to help people understand and monitor the environment around them. This repository contains the **backend API** that powers the platform.

The backend is a layered, production-oriented **FastAPI** service: authenticated users manage **projects**, spin up **AI agents** inside them, and hold **conversations** with those agents through an interchangeable **LLM provider** abstraction. It also ingests real-time **environmental data** (weather + air quality) from external providers and exposes it through versioned query endpoints.


---

## ✨ Features

- **🔐 Authentication & security**
  - `register` / `login` / `me` with JWT bearer authentication
  - bcrypt password hashing with a strict password policy (12+ chars, upper/lower/digit/special)
  - Email normalization, constant-time credential comparison, secret-key validation
- **📁 Project management** — create, list, update, and soft-delete (archive) projects with strict per-user ownership
- **🤖 AI Agents** — create, configure, list, update, and archive agents scoped to a project (model, temperature, system prompt, JSON config)
- **💬 Conversations** — per-project chat history with **persistent messages** and an LLM-powered reply flow
- **🌍 Environmental intelligence** — automatic ingestion of weather (OpenWeather) and air quality (OpenAQ) data, with historical latest/geofence query endpoints and optional Celery-based scheduled collection
- **🧩 Pluggable AI providers** — `LLMProvider` ABC with an OpenAI implementation behind a factory, so providers can be swapped/extended
- **🆓 Free LLM by default** — when `OPENROUTER_API_KEY` is set, agent replies are served by **free Nemotron models via OpenRouter** instead of the paid OpenAI API (default model `nvidia/nemotron-4-340b-base`, overridable with `LLM_MODEL`)
- **🛠️ Engineering standards**
  - Versioned API under `/api/v1`
  - Layered architecture: `api → services → repositories → models`
  - Centralized dependency and exception architecture with consistent error payloads
  - Structured logging with request IDs and sensitive-data redaction
  - Environment-aware configuration (development / testing / production)
- **🧪 Comprehensive test suite** (60+ tests) run against an in-memory database

---

## 🏗️ Tech Stack

| Layer | Technology |
|-------|------------|
| Web framework | [FastAPI](https://fastapi.tiangolo.com/) |
| Data validation | [Pydantic v2](https://docs.pydantic.dev/) + pydantic-settings |
| ORM | [SQLAlchemy 2.x](https://www.sqlalchemy.org/) |
| Migrations | [Alembic](https://alembic.sqlalchemy.org/) |
| Database | [PostgreSQL 17](https://www.postgresql.org/) |
| Auth | [python-jose](https://python-jose.readthedocs.io/) (JWT) + [passlib/bcrypt](https://passlib.readthedocs.io/) |
| AI | [OpenAI SDK](https://github.com/openai/openai-python) (behind an abstraction) |
| Testing | [pytest](https://docs.pytest.org/) + FastAPI `TestClient` |
| Server | [uvicorn](https://www.uvicorn.org/) |

---

## 📁 Project Structure

```
AetherLab/
├── backend/
│   ├── alembic/                  # Database migrations
│   │   └── versions/             #   one revision per schema change
│   ├── app/
│   │   ├── ai/                   # LLM provider abstraction
│   │   │   └── providers/        #   base ABC + OpenAI implementation
│   │   ├── api/v1/endpoints/     # Versioned HTTP routes
│   │   ├── core/                 # Config, security, logging
│   │   ├── db/                   # Engine, session, declarative base
│   │   ├── dependencies/         # Reusable FastAPI dependencies
│   │   ├── exceptions/           # Domain exceptions + global handlers
│   │   ├── models/               # SQLAlchemy ORM models
│   │   ├── repositories/         # Data-access layer
│   │   ├── schemas/              # Pydantic request/response models
│   │   └── services/             # Business-logic layer
│   └── tests/                    # pytest suite
├── .env.example                  # Environment variable template
├── requirements.txt
└── README.md
```

The **layered architecture** keeps concerns separated and testable:

```
HTTP Request
     │
     ▼
api/v1/endpoints  (routing, auth, validation)
     │
     ▼
services          (business logic, orchestration)
     │
     ▼
repositories      (data access / queries)
     │
     ▼
models            (SQLAlchemy ORM)
     │
     ▼
PostgreSQL
```
---

## 🚀 Getting Started

### Prerequisites

- **Python 3.11+**
- **PostgreSQL 17** running locally (or a remote instance)
- Redis is optional (used for future caching/queues)

### 1. Clone & install

```bash
git clone https://github.com/721189/AetherLab.git
cd AetherLab/backend

python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r ../requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
```

Then edit `.env` with your values (especially `DATABASE_URL` and `SECRET_KEY`).

### 3. Set up the database & run migrations

```bash
cd backend
alembic upgrade head
```

This applies all schema migrations (users, projects, agents, conversations, messages).

### 4. Run the API

```bash
cd backend
uvicorn app.main:app --reload
```

The API is now live at `http://localhost:8000`. Interactive docs:

- Swagger UI: <http://localhost:8000/docs>
- ReDoc: <http://localhost:8000/redoc>

### 5. Run the tests

```bash
cd backend
pytest
```

Tests use an in-memory SQLite database via a dependency override — **no live PostgreSQL or API keys are required**.

---

## 🔌 API Reference

All endpoints are namespaced under `/api/v1`.

### Authentication (`/api/v1/auth`)

| Method | Endpoint  | Description                     | Auth |
|--------|-----------|---------------------------------|------|
| POST   | `/register` | Create a new user             | —    |
| POST   | `/login`    | Obtain a JWT access token     | —    |
| GET    | `/me`       | Return the current user       | ✅   |

### Projects (`/api/v1/projects`)

| Method | Endpoint            | Description                          | Auth |
|--------|---------------------|--------------------------------------|------|
| POST   | `/`                 | Create a project                     | ✅   |
| GET    | `/`                 | List own projects                    | ✅   |
| GET    | `/{id}`             | Get a project (owner only)           | ✅   |
| PATCH  | `/{id}`             | Update a project                     | ✅   |
| DELETE | `/{id}`             | Archive (soft-delete) a project      | ✅   |

### Agents (`/api/v1/projects/{project_id}/agents`)

| Method | Endpoint  | Description                     | Auth |
|--------|-----------|---------------------------------|------|
| POST   | `/`       | Create an agent in a project    | ✅   |
| GET    | `/`       | List agents in a project        | ✅   |
| GET    | `/{id}`   | Get an agent (owner only)       | ✅   |
| PATCH  | `/{id}`   | Update an agent                 | ✅   |
| DELETE | `/{id}`   | Archive an agent                | ✅   |

### Conversations (`/api/v1/projects/{project_id}/conversations`)

| Method | Endpoint              | Description                        | Auth |
|--------|-----------------------|------------------------------------|------|
| POST   | `/`                   | Create a conversation in a project | ✅   |
| GET    | `/`                   | List conversations in a project    | ✅   |
| GET    | `/{conv_id}`          | Get a conversation (owner only)    | ✅   |
| PATCH  | `/{conv_id}`          | Update a conversation title        | ✅   |
| DELETE | `/{conv_id}`          | Delete a conversation              | ✅   |
| POST   | `/{conv_id}/messages` | Send a message & get an AI reply   | ✅   |

### Quick start flow

```bash
# 1. Register
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email": "you@example.com", "password": "StrongPass123!"}'

# 2. Login
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "you@example.com", "password": "StrongPass123!"}'
# → returns {"access_token": "...", "refresh_token": "...", "token_type": "bearer"}

TOKEN="<access_token>"

# 2b. Rotate the refresh token (revokes the presented token, issues a new pair)
curl -X POST http://localhost:8000/api/v1/auth/refresh \
  -H "Content-Type: application/json" \
  -d '{"refresh_token": "<refresh_token>"}'

# 3. Create a project
curl -X POST http://localhost:8000/api/v1/projects/ \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "My First Project", "description": "Monitoring station"}'

# 4. Create an agent
curl -X POST http://localhost:8000/api/v1/projects/1/agents \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "Weather Analyst", "model": "gpt-4o", "temperature": 0.4}'

# 5. Start a conversation and chat
curl -X POST http://localhost:8000/api/v1/projects/1/conversations \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"title": "Environment chat"}'

curl -X POST http://localhost:8000/api/v1/projects/1/conversations/1/messages \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"content": "Summarize today air quality trends."}'

# 6. Query environmental intelligence
curl "http://localhost:8000/api/v1/environmental/latest?location_name=Delhi"
curl "http://localhost:8000/api/v1/environmental/historical?location_name=Delhi&hours=24"
```
---

## ⚙️ Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `APP_NAME` | Application name shown in docs | `AetherLab API` |
| `APP_ENV` | `development`, `testing`, or `production` | `development` |
| `DEBUG` | Enable debug-level logging | `False` |
| `DATABASE_URL` | SQLAlchemy PostgreSQL connection string | — (required) |
| `SECRET_KEY` | JWT signing key (min 32 chars, never default) | — (required) |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | JWT lifetime in minutes | `30` |
| `REFRESH_TOKEN_EXPIRE_MINUTES` | Refresh-token lifetime in minutes | `10080` (7 days) |
| `REDIS_URL` | Redis connection string | `redis://localhost:6379/0` |
| `OPENROUTER_API_KEY` | **Preferred** LLM provider key (free Nemotron via OpenRouter) | — |
| `OPENROUTER_SITE_URL` | Your app URL sent to OpenRouter | `https://aetherlab.app` |
| `LLM_MODEL` | Default model for agent replies (free Nemotron) | `nvidia/nemotron-4-340b-base` |
| `OPENAI_API_KEY` | *Fallback* LLM provider — **paid**, remove if you use OpenRouter | — |
| `OPENWEATHER_API_KEY` | Required only for weather ingestion | — |
| `OPENAQ_API_KEY` | Required only for air-quality ingestion | — |

> 💡 **Keep AI free:** set `OPENROUTER_API_KEY` and leave `OPENAI_API_KEY` empty. The factory always prefers OpenRouter when its key is present, so agent replies use free Nemotron models and never bill you.


> **Security:** never commit real `.env` values. The repo ignores all `.env*` files; only the `.env.example` template is tracked. Rotate `SECRET_KEY` and API keys before production.

---

## 🧪 Testing

The suite covers the full vertical slice — **register → login → create project → agents → conversations → AI reply** — plus negative cases (wrong credentials, cross-user access, invalid payloads, expired/invalid tokens).

```bash
cd backend
pytest -v        # 72 tests
pytest tests/test_auth.py -v
pytest tests/test_conversations.py -v
pytest tests/test_environmental.py -v
```

Tests run against an in-memory SQLite database and a **mocked LLM provider**, so they are fast, deterministic, and require **no external services**.

---

## 🗂️ Database Migrations

Migrations are managed with Alembic:

```bash
cd backend

# Create a new migration after changing models
alembic revision --autogenerate -m "describe change"

# Apply pending migrations
alembic upgrade head

# Roll back the last migration
alembic downgrade -1

# Inspect migration history
alembic history
```

Current schema (`head` = `f7a3b2c5d9e1`):

```
users → projects → agents
                  └→ conversations → messages
environmental_readings  (weather + air-quality snapshots)
```

---

## 🛣️ Roadmap

- Streaming chat responses (`stream_response` on the provider layer)
- Agent ↔ conversation association and per-agent system prompts
- Tool use / function calling for agents
- Additional LLM providers (Anthropic, local models) via the factory
- Pagination metadata envelope for list endpoints
- Containerized deployment (Docker Compose) with production logging

---

## 📄 License

This project is licensed under the terms found in the [LICENSE](/LICENSE) file.

