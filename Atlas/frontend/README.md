# Frontend (Atlas)

ChatGPT-like UI for the standalone Atlas backend.

The frontend talks **only** to the Atlas backend (`/atlas/*`, `/health*`).
It never calls Zoom Agentic AI directly; the Atlas backend forwards every
request over REST.

## Stack

- React 18 + Vite 5 + TypeScript
- `react-markdown` + `remark-gfm` for assistant message rendering
- Native `fetch` + `ReadableStream` for SSE streaming chat (no buffering)

## Run

```bash
npm install
cp .env.example .env
npm run dev          # http://localhost:5173
```

The dev server proxies `/atlas` and `/health` to `VITE_ATLAS_API_BASE`
(default `http://localhost:8090`). In dev the API is relative; in prod set
`VITE_ATLAS_API_BASE` to the deployed Atlas origin.

## Build

```bash
npm run build        # tsc -b && vite build -> dist/
npm run preview      # serve the built bundle
```

## Features

- Conversation list / create / rename / delete (sidebar)
- Chat with the selected conversation
- Streaming responses via `POST /atlas/conversations/{id}/chat/stream`
- Markdown rendering (headings, lists, tables, code blocks, bold/italic)
- Citation display
- Loading + typing indicators
- Error handling
- Dark mode (system + manual toggle)
- Responsive layout
