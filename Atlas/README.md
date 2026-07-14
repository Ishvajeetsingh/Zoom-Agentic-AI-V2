# Standalone Atlas

Standalone Atlas repository for the Zoom Agentic AI migration.

This repository consumes **Zoom Agentic AI strictly through HTTP REST APIs**.
It does **not** import any Zoom internals (repositories, ORM models, database
sessions, meeting/question services, embedding / ranking / semantic-retrieval
services, processing pipeline, or any other private utility).

## Repository layout

```
Atlas/
  frontend/        # future: standalone Atlas UI
  backend/         # HTTP-client-driven Atlas server
    app/
      api/         # FastAPI routers that re-expose Atlas concerns
      clients/     # typed HTTP clients for Zoom Agentic AI REST endpoints
      services/    # orchestration built on top of clients (Phase 4+)
      models/      # Pydantic / dataclass view models (no ORM)
      schemas/     # request / response schemas
      core/        # config, logging, http base
        config/
    main.py
    requirements.txt
  docs/            # design + API notes
  deployment/      # docker-compose, Dockerfiles, deployment configs
  README.md
  .gitignore
  requirements.txt
  .env.example
  docker-compose.yml
```

## Scope

Phase 3 (this commit) delivers **only the scaffold**:

- Directory structure
- Configuration (`ATLAS_API_BASE_URL`, `API_TIMEOUT`, `API_KEY`, retry settings)
- Reusable typed HTTP clients for the existing REST endpoints
- A minimal FastAPI `main.py` that boots and exposes `/health`
- Container + env scaffolding

It intentionally does **not** migrate:

- Educational Intelligence
- Prompt builders
- Memory / streaming / citations
- Conversation services
- Ollama integration
- Frontend

Those land in subsequent phases.

## Running

```
cd backend
pip install -r requirements.txt
cp ../.env.example ../.env   # then edit values
uvicorn app.main:app --reload --port 8090
```

Point `ATLAS_API_BASE_URL` at your Zoom Agentic AI deployment
(default: `http://localhost:8000/api/v1`).

## Relationship to Zoom Agentic AI

The integrated Atlas inside Zoom Agentic AI is the **production baseline** and
remains untouched. This standalone repo is **additive**: it talks to the
baseline via REST only. Both systems must keep working independently.
