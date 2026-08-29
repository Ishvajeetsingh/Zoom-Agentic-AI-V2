import { useEffect, useState } from "react";
import { CheckCircle2, RotateCcw } from "lucide-react";

import { AppShell } from "../components/layout/AppShell";
import { LoadingState } from "../components/common/LoadingState";
import { ErrorState } from "../components/common/ErrorState";
import { EmptyState } from "../components/common/EmptyState";

import { getPublicTranscriptQuestions } from "../api/questions";
import type { Question } from "../types/api";

interface PublicResultsPageProps {
  transcriptId: string;
}

export function PublicResultsPage({
  transcriptId,
}: PublicResultsPageProps) {
  const [questions, setQuestions] = useState<Question[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    setLoading(true);
    setError(null);

    getPublicTranscriptQuestions(transcriptId)
      .then((response) => {
        if (cancelled) {
          return;
        }

        setQuestions(response.items);
        setLoading(false);
      })
      .catch((err) => {
        if (cancelled) {
          return;
        }

        setError(
          err instanceof Error
            ? err.message
            : "Failed to load generated questions."
        );
        setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [transcriptId]);

  return (
    <AppShell>
      <div className="page-header">
        <h1>Generated Questions</h1>
        <p className="page-header-subtitle">
          AI-generated assessment questions from your uploaded transcript
        </p>
      </div>

      {loading && (
        <LoadingState message="Loading generated questions..." />
      )}

      {error && (
        <ErrorState message={error} />
      )}

      {!loading && !error && questions.length === 0 && (
        <EmptyState
          title="No Questions Available"
          message="The transcript was processed, but no generated questions were found."
        />
      )}

      {!loading && !error && questions.length > 0 && (
        <>
          <div className="panel" style={{ marginBottom: 20 }}>
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                gap: 16,
                flexWrap: "wrap",
              }}
            >
              <div>
                <h2 style={{ margin: 0 }}>
                  Assessment Results
                </h2>

                <p
                  className="text-muted"
                  style={{ marginBottom: 0 }}
                >
                  {questions.length} generated question
                  {questions.length === 1 ? "" : "s"}
                </p>
              </div>

              <a
                href="#/upload-transcript"
                className="btn-secondary"
              >
                <RotateCcw size={16} />
                Process Another Transcript
              </a>
            </div>
          </div>

          <div
            style={{
              display: "grid",
              gap: 20,
            }}
          >
            {questions.map((question, index) => (
              <div
                key={question.id}
                className="panel"
              >
                <div
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "flex-start",
                    gap: 16,
                    marginBottom: 16,
                  }}
                >
                  <div>
                    <div
                      className="text-muted"
                      style={{
                        fontSize: 13,
                        marginBottom: 6,
                      }}
                    >
                      Question {index + 1}
                    </div>

                    <h3 style={{ margin: 0 }}>
                      {question.question_text}
                    </h3>
                  </div>

                  <div
                    style={{
                      display: "flex",
                      gap: 8,
                      flexWrap: "wrap",
                    }}
                  >
                    {question.difficulty && (
                      <span className="badge">
                        {question.difficulty}
                      </span>
                    )}

                    {question.bloom_taxonomy && (
                      <span className="badge">
                        {question.bloom_taxonomy}
                      </span>
                    )}
                  </div>
                </div>

                {question.options.length > 0 && (
                  <div
                    style={{
                      display: "grid",
                      gap: 10,
                      marginBottom: 18,
                    }}
                  >
                    {question.options.map((option, optionIndex) => {
                      const isCorrect =
                        option === question.correct_answer;

                      return (
                        <div
                          key={`${question.id}-${optionIndex}`}
                          style={{
                            display: "flex",
                            gap: 10,
                            alignItems: "flex-start",
                            padding: 12,
                            border: "1px solid var(--border-color)",
                            borderRadius: 8,
                          }}
                        >
                          {isCorrect && (
                            <CheckCircle2
                              size={18}
                              style={{
                                flexShrink: 0,
                                marginTop: 1,
                              }}
                            />
                          )}

                          <div>
                            <strong>
                              {String.fromCharCode(
                                65 + optionIndex
                              )}
                              .
                            </strong>{" "}
                            {option}

                            {isCorrect && (
                              <div
                                style={{
                                  fontSize: 12,
                                  marginTop: 4,
                                }}
                              >
                                Correct answer
                              </div>
                            )}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}

                <div
                  style={{
                    borderTop:
                      "1px solid var(--border-color)",
                    paddingTop: 14,
                  }}
                >
                  <strong>Explanation</strong>

                  <p style={{ marginBottom: 0 }}>
                    {question.explanation}
                  </p>
                </div>

                {(question.category ||
                  question.educational_score != null ||
                  question.relevance_score != null) && (
                  <div
                    className="text-muted"
                    style={{
                      display: "flex",
                      gap: 16,
                      flexWrap: "wrap",
                      marginTop: 14,
                      fontSize: 13,
                    }}
                  >
                    {question.category && (
                      <span>
                        Category: {question.category}
                      </span>
                    )}

                    {question.educational_score != null && (
                      <span>
                        Educational score:{" "}
                        {question.educational_score}
                      </span>
                    )}

                    {question.relevance_score != null && (
                      <span>
                        Relevance score:{" "}
                        {question.relevance_score}
                      </span>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
        </>
      )}
    </AppShell>
  );
}