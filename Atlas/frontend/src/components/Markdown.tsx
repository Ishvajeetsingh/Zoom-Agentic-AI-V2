import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { Components } from "react-markdown";
import { extractCitations } from "@/lib/citations";

interface MarkdownProps {
  content: string;
}

/**
 * Markdown renderer with GFM support (headings, lists, tables, code blocks,
 * bold/italic) plus inline citation markers: a ``[1]`` (numeric) marker is
 * rendered as a small badge that scrolls to the matching citation below.
 */
export function Markdown({ content }: MarkdownProps) {
  const [copied, setCopied] = useState<string | null>(null);

  // Map numeric marker -> citation index (1-based). If structured citations
  // are supplied by the backend we use their order, otherwise infer from text.
  const markers = extractCitations(content);

  const components: Components = {
    code(props) {
      const { className, children } = props;
      const isBlock = /language-/.test(className ?? "");
      const code = String(children ?? "");
      const lang = (className ?? "").replace("language-", "") || "text";

      if (!isBlock) {
        return <code className={className}>{children}</code>;
      }

      const copy = async () => {
        try {
          await navigator.clipboard.writeText(code);
          setCopied(lang);
          setTimeout(() => setCopied(null), 1200);
        } catch {
          /* ignore */
        }
      };

      return (
        <>
          <div className="md__code-header">
            <span>{lang}</span>
            <button className="md__code-copy" onClick={copy} type="button">
              {copied === lang ? "Copied" : "Copy"}
            </button>
          </div>
          <pre>
            <code className={className}>{children}</code>
          </pre>
        </>
      );
    },
    a({ children, ...rest }) {
      // Numbered link text like "[1]" -> render as a citation badge.
      const text = String(children ?? "");
      const idx = markers.indexOf(text);
      if (/^\[\d+\]$/.test(text) && idx !== -1) {
        const num = idx + 1;
        return (
          <a
            className="md__cite"
            href={`#citation-${num}`}
            onClick={(e) => {
              e.preventDefault();
              const el = document.getElementById(`citation-${num}`);
              el?.scrollIntoView({ behavior: "smooth", block: "center" });
            }}
            title={`Citation ${num}`}
          >
            {num}
          </a>
        );
      }
      return <a {...rest} target="_blank" rel="noreferrer noopener">{children}</a>;
    },
  };

  return (
    <div className="md">
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
        {content}
      </ReactMarkdown>
    </div>
  );
}
