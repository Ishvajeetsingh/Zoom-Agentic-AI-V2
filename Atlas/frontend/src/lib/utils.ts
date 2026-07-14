// Small shared helpers used by the API client and hooks.

export function classNames(...parts: Array<string | false | null | undefined>): string {
  return parts.filter(Boolean).join(" ");
}

export function nowIso(): string {
  return new Date().toISOString();
}

// Parse an SSE `data:` frame body into the JSON shape used by chat/stream.
// The upstream baseline emits `data: {"text": "..."}` frames; some frames
// may carry citations under `citations` or `sources`. We forward everything
// we understand and fall back to the raw string on parse failure.
export interface StreamFrame {
  text?: string;
  citations?: unknown;
  [key: string]: unknown;
}

export function parseStreamFrame(raw: string): StreamFrame | null {
  if (!raw) return null;
  try {
    return JSON.parse(raw) as StreamFrame;
  } catch {
    // Not JSON — treat the payload as plain text.
    return { text: raw };
  }
}
