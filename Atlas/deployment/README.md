# Standalone Atlas - deployment configs

## Local

```
cp ../.env.example ../.env   # fill values
docker compose -f ../docker-compose.yml up --build
```

The standalone backend reaches out to a separately-running Zoom Agentic
AI deployment. Point `ATLAS_API_BASE_URL` at it (default:
`http://host.docker.internal:8000/api/v1` when running with Docker
Compose, or `http://localhost:8000/api/v1` when running the backend on
the host directly).

## Health checks

- `GET /health`          -> local liveness
- `GET /health/upstream` -> reach Zoom Agentic AI `/api/v1/health` over the
                              shared HTTP client (validates config + auth)

## Future work (later phases)

- TLS termination
- secrets (managed API keys, vault integration)
- horizontal scaling
- ui / SSE passthrough wiring
