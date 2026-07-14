# Standalone Atlas - architecture notes

## Principle

*Standalone Atlas is a separate process; Zoom Agentic AI remains the
production baseline. Standalone Atlas is additive.* If the baseline
exists and exposes the REST inventory in `docs/API_INVENTORY.md`, the
standalone backend must work end-to-end without importing a single Zoom
Agentic AI symbol.

## Layering

```
FastAPI routes (app/api/)
      |
      v
High-level services (app/services/)  [Phase 4+]
      |
      v
Typed HTTP clients (app/clients/)
      |
      v
BaseHTTPClient (transport: timeout, auth, retry)
      |
      v
Zoom Agentic AI REST API (external process)
```

Each layer only knows about the layer immediately below it. No client
returns a Zoom ORM object; only JSON. Services (Phase 4+) will compose
multiple client calls into Atlas-level domain workflows (educational
intelligence, quiz building, citations, memory, streaming, etc.) without
ever importing Zoom Agentic AI Python code.

## Settings

Single source of truth: `app/core/config/settings.py`. All clients read
`ATLAS_API_BASE_URL`, `ATLAS_API_TIMEOUT`, `ATLAS_API_KEY`, and the
retry knobs from there. Tests can call `reset_settings()` after mutating
environment variables.
