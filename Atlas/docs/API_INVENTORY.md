# Standalone Atlas - design notes

## Boundary

Standalone Atlas consumes **Zoom Agentic AI strictly via REST**. It does
**not** import any of:

- repositories
- ORM models
- database sessions
- EmbeddingService / ProfessorRankingService / SemanticRetrievalService
- meeting / question services
- the processing pipeline
- any internal utility

## REST endpoints consumed (Phase 1 inventory)

All paths are prefixed with the configured `ATLAS_API_BASE_URL`
(default `http://localhost:8000/api/v1`).

### Meetings
- `GET /meetings`
- `GET /meetings/{meeting_id}`

### Transcripts (+ insights router shares `transcripts` prefix)
- `GET /transcripts`
- `GET /transcripts/{transcript_id}`
- `GET /transcripts/{transcript_id}/questions`
- `GET /transcripts/{transcript_id}/summary`
- `GET /transcripts/{transcript_id}/key-concepts`
- `GET /transcripts/{transcript_id}/action-items`
- `GET /transcripts/{transcript_id}/outputs`
- `GET /transcripts/{transcript_id}/outputs/count`
- `GET /transcripts/{transcript_id}/key-takeaways`
- `GET /transcripts/{transcript_id}/learning-outcomes`
- `GET /transcripts/{transcript_id}/topics`
- `GET /transcripts/{transcript_id}/decisions`
- `GET /transcripts/{transcript_id}/recommendations`
- `GET /transcripts/{transcript_id}/full-insights`

### Questions
- `GET /questions/{question_id}`

### Atlas-proxy (Phase 2 - new)
- `POST /retrieval/search`
- `GET /meetings/{meeting_id}/ranked-questions`
- `GET /transcripts/{transcript_id}/ranked-questions`

### Atlas (conversation/chat)
- `POST   /atlas/conversations`
- `GET    /atlas/conversations`
- `GET    /atlas/conversations/{conversation_id}`
- `PATCH  /atlas/conversations/{conversation_id}`
- `DELETE /atlas/conversations/{conversation_id}`
- `POST   /atlas/conversations/{conversation_id}/messages`
- `POST   /atlas/conversations/{conversation_id}/chat`
- `POST   /atlas/conversations/{conversation_id}/chat/stream`

### Health
- `GET /health`
- `GET /ready`
- `GET /ollama`

## Client mapping (this repo)

| Client            | Routes wrapped                                       |
|-------------------|------------------------------------------------------|
| MeetingClient     | `/meetings`, `/meetings/{id}`                        |
| TranscriptClient  | `/transcripts`, `/transcripts/{id}`, `/transcripts/{id}/questions` |
| InsightsClient    | all per-transcript insight GETs listed above         |
| QuestionClient    | `/questions/{id}`                                    |
| RankingClient     | `/meetings/{id}/ranked-questions`, `/transcripts/{id}/ranked-questions` |
| RetrievalClient   | `POST /retrieval/search`                             |
| AtlasClient       | all `/atlas/conversations*` routes                   |

## Phase plan

- Phase 1: architecture analysis (done)
- Phase 2: REST proxy endpoints on Zoom Agentic AI (done)
- Phase 3: this scaffold + typed HTTP clients (done)
- Phase 4+: educational intelligence, prompt builders, memory, streaming,
  citations, conversation orchestration, frontend migration.
