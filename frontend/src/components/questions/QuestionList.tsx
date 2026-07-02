import { useEffect, useState } from "react";
import { getTranscriptQuestions } from "../../api/questions";
import type { Question, PaginatedListResponse } from "../../types/api";
import { QuestionCard } from "./QuestionCard";
import { QuestionFilters, type QuestionFilterValues } from "./QuestionFilters";
import { EmptyState } from "../common/EmptyState";
import { ErrorState } from "../common/ErrorState";
import { LoadingState } from "../common/LoadingState";

const PAGE_SIZE = 20;

interface QuestionListProps {
  transcriptId: string;
  mcqOnly?: boolean;
  onFiltersChange?: (filters: QuestionFilterValues) => void;
}

export function QuestionList({ transcriptId, mcqOnly, onFiltersChange }: QuestionListProps) {
  const [data, setData] = useState<PaginatedListResponse<Question> | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [offset, setOffset] = useState(0);
  const [filters, setFilters] = useState<QuestionFilterValues>({
    difficulty: "",
    question_type: mcqOnly ? "mcq" : "",
    category: "",
    bloom: "",
    top_n: "",
    order: "asc",
  });

  useEffect(() => {
    if (onFiltersChange) {
      onFiltersChange(filters);
    }
  }, [filters, onFiltersChange]);
  const [showAnswers, setShowAnswers] = useState(false);

  useEffect(() => {
    setOffset(0);
  }, [filters]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    const apiFilters: Record<string, string | number> = {
      offset,
      limit: filters.top_n ? Number(filters.top_n) : PAGE_SIZE,
      order: filters.order,
    };
    if (filters.difficulty) apiFilters.difficulty = filters.difficulty;
    if (filters.question_type) apiFilters.question_type = filters.question_type;
    if (filters.category) apiFilters.category = filters.category;
    if (filters.bloom) apiFilters.bloom = filters.bloom;
    if (filters.top_n) apiFilters.top = Number(filters.top_n);

    getTranscriptQuestions(transcriptId, apiFilters)
      .then((res) => {
        if (!cancelled) {
          setData(res);
          setLoading(false);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to load questions");
          setLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [transcriptId, offset, filters]);

  const totalPages = data ? Math.ceil(data.total / (filters.top_n ? Number(filters.top_n) : PAGE_SIZE)) : 0;
  const currentPage = data ? Math.floor(data.offset / (filters.top_n ? Number(filters.top_n) : PAGE_SIZE)) + 1 : 1;

  if (loading) return <LoadingState message="Loading questions..." />;
  if (error) return <ErrorState message={error} />;
  if (!data || data.items.length === 0) return <EmptyState message="No questions found." title="No Questions" />;

  return (
    <div className="question-list-container">
      <div className="question-list-toolbar">
        <QuestionFilters filters={filters} onChange={setFilters} hideTypeFilter={mcqOnly} />
        <label className="toggle-answers">
          <input type="checkbox" checked={showAnswers} onChange={(e: { target: { checked: boolean } }) => setShowAnswers(e.target.checked)} />
          Show Answers
        </label>
      </div>

      <div className="question-list-items">
        {data.items.map((q: Question, i: number) => (
          <QuestionCard key={q.id} question={q} showAnswer={showAnswers} index={offset + i} />
        ))}
      </div>

      {!filters.top_n && totalPages > 1 && (
        <div className="pagination">
          <button
            className="pagination-btn"
            disabled={currentPage <= 1}
            onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
          >
            Previous
          </button>
          <span className="pagination-info">
            Page {currentPage} of {totalPages} ({data.total} questions)
          </span>
          <button
            className="pagination-btn"
            disabled={currentPage >= totalPages}
            onClick={() => setOffset(offset + PAGE_SIZE)}
          >
            Next
          </button>
        </div>
      )}
    </div>
  );
}
