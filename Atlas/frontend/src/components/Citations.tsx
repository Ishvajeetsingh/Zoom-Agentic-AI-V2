import type { Citation } from "@/types";
import { indexCitations } from "@/lib/citations";

interface CitationsProps {
  content: string;
  citations?: Citation[];
}

/**
 * Render the citations/sources list at the foot of an assistant message.
 * Uses :func:`indexCitations` to honour backend-supplied citations when
 * present and otherwise synthesises entries from ``[n]`` markers in text.
 */
export function Citations({ content, citations = [] }: CitationsProps) {
  const items = indexCitations(content, citations);
  if (items.length === 0) return null;

  return (
    <div className="citations">
      <div className="citations__title">Sources</div>
      <ol className="citations__list">
        {items.map((c) => (
          <li key={`citation-${c.index}`} id={`citation-${c.index}`} className="citation">
            <span className="citation__index">{c.index}</span>
            <div className="citation__text">
              {c.source && <span className="citation__source">{String(c.source)}</span>}
              {c.snippet && (
                <>
                  {c.source ? " — " : null}
                  <span>{String(c.snippet)}</span>
                </>
              )}
              {c.url && (
                <>
                  {" — "}
                  <a
                    href={String(c.url)}
                    target="_blank"
                    rel="noreferrer noopener"
                    style={{ wordBreak: "break-all" }}
                  >
                    link
                  </a>
                </>
              )}
              {!c.source && !c.snippet && !c.url
                ? String(c.id ?? `Citation ${c.index}`)
                : null}
            </div>
          </li>
        ))}
      </ol>
    </div>
  );
}
