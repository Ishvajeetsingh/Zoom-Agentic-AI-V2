// Citation extraction + rendering helpers.
//
// The backend's assistant messages may contain inline citation markers
// (e.g. ``[1]``, ``[Smith 2023]``) plus an optional citations/sources array
// on the final frame. We normalise everything into a stable list and a
// function that turns markers into numbered references.

import type { Citation } from "@/types";

export interface ParsedCitations {
  // Ordered list of unique citations referenced in the text.
  items: Array<Citation & { index: number }>;
  // The text with citation markers replaced by reference indices secured.
  // (We don't mutate the text here; the Markdown renderer handles visual
  // markers. This is left for completeness and future use.)
}

const MARKER_RE = /\[(?:([0-9]+)|([A-Za-z][\w .,\-:;]*?))\]/g;

/** Extract unique citation markers in order of first appearance. */
export function extractCitations(text: string): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const m of text.matchAll(MARKER_RE)) {
    const key = m[0];
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(key);
  }
  return out;
}

/** Attach indices to an existing citations array using marker order. */
export function indexCitations(
  text: string,
  raw: Citation[] = [],
): Array<Citation & { index: number }> {
  // If the backend already supplied structured citations, prefer them.
  if (raw.length > 0) {
    return raw.map((c, i) => ({ ...c, index: i + 1 }));
  }
  // Otherwise synthesise minimal citation entries from the inline markers.
  const markers = extractCitations(text);
  return markers.map((marker, i) => ({
    id: marker,
    source: marker,
    index: i + 1,
  }));
}
