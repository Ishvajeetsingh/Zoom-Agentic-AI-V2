import { useEffect, useState, useMemo, useCallback } from "react";
import {
  BookOpen,
  Layers,
  HelpCircle,
  CheckSquare,
  Search,
  Filter,
  ChevronLeft,
  ChevronRight,
  ExternalLink,
  RotateCcw,
} from "lucide-react";
import { AppShell } from "../components/layout/AppShell";
import { LoadingState } from "../components/common/LoadingState";
import { ErrorState } from "../components/common/ErrorState";
import { EmptyState } from "../components/common/EmptyState";
import { getMeetings } from "../api/meetings";
import { getTranscripts } from "../api/transcripts";
import { getTranscriptQuestions } from "../api/questions";
import {
  getLearningOutputs,
  getOutputCounts,
} from "../api/insights";
import type { MeetingListItem, TranscriptListItem, Question } from "../types/api";
import type {
  LearningOutputItem,
  OutputCountItem,
} from "../api/insights";

const PAGE_SIZE = 10;
const ITEM_PAGE_SIZE = 20;

type OutputType = "all" | "flashcard" | "short_question" | "mcq";

interface MeetingLearningData {
  meeting: MeetingListItem;
  transcriptId: string;
  flashcards: LearningOutputItem[];
  shortQuestions: LearningOutputItem[];
  mcqs: Question[];
  counts: OutputCountItem[];
  totalFlashcards: number;
  totalShortQuestions: number;
  totalMcqs: number;
  fcOffset: number;
  sqOffset: number;
  fcLoading: boolean;
  sqLoading: boolean;
}

function formatRelativeTime(dateStr: string | null): string {
  if (!dateStr) return "\u2014";
  const date = new Date(dateStr);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffSec = Math.floor(diffMs / 1000);
  if (diffSec < 60) return "just now";
  const diffMin = Math.floor(diffSec / 60);
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffHr = Math.floor(diffMin / 60);
  if (diffHr < 24) return `${diffHr}h ago`;
  const diffDay = Math.floor(diffHr / 24);
  if (diffDay < 7) return `${diffDay}d ago`;
  return date.toLocaleDateString();
}

function FlashcardItem({ item, index }: { item: LearningOutputItem; index: number }) {
  const [flipped, setFlipped] = useState(false);
  const front = (item.content?.front as string) ?? "";
  const back = (item.content?.back as string) ?? "";
  const category = item.content?.category as string | null;

  return (
    <div
      className={`learning-flashcard ${flipped ? "flipped" : ""}`}
      onClick={() => setFlipped(!flipped)}
    >
      <div className="learning-flashcard-inner">
        <div className="learning-flashcard-front">
          <div className="learning-flashcard-index">F{index + 1}</div>
          <p className="learning-flashcard-text">{front}</p>
          {category && (
            <span className="badge badge-type">{category}</span>
          )}
          <span className="learning-flashcard-hint">Click to flip</span>
        </div>
        <div className="learning-flashcard-back">
          <div className="learning-flashcard-index">F{index + 1}</div>
          <p className="learning-flashcard-text">{back}</p>
          {item.difficulty && (
            <span className={`badge badge-difficulty-${item.difficulty}`}>
              {item.difficulty}
            </span>
          )}
          <span className="learning-flashcard-hint">Click to flip</span>
        </div>
      </div>
    </div>
  );
}

function ShortQuestionItem({ item, index }: { item: LearningOutputItem; index: number }) {
  const [showAnswer, setShowAnswer] = useState(false);
  const questionText = (item.content?.question_text as string) ?? "";
  const sampleAnswer = (item.content?.sample_answer as string) ?? "";

  return (
    <div className="learning-sq-card">
      <div className="learning-sq-header">
        <span className="learning-sq-index">Q{index + 1}</span>
        {item.difficulty && (
          <span className={`badge badge-difficulty-${item.difficulty}`}>
            {item.difficulty.charAt(0).toUpperCase() + item.difficulty.slice(1)}
          </span>
        )}
        <span className="badge badge-type">Short Answer</span>
      </div>
      <p className="learning-sq-question">{questionText}</p>
      {showAnswer ? (
        <div className="learning-sq-answer">
          <p className="learning-sq-answer-label">Sample Answer:</p>
          <p className="learning-sq-answer-text">{sampleAnswer}</p>
        </div>
      ) : (
        <button
          className="btn-secondary"
          style={{ fontSize: "0.8rem", padding: "6px 12px" }}
          onClick={() => setShowAnswer(true)}
        >
          Show Answer
        </button>
      )}
    </div>
  );
}

function McqItem({ question, index }: { question: Question; index: number }) {
  const [showAnswer, setShowAnswer] = useState(false);

  return (
    <div className="learning-sq-card">
      <div className="learning-sq-header">
        <span className="learning-sq-index">Q{index + 1}</span>
        <span className={`badge badge-difficulty-${question.difficulty}`}>
          {question.difficulty.charAt(0).toUpperCase() +
            question.difficulty.slice(1)}
        </span>
        <span className="badge badge-type">MCQ</span>
      </div>
      <p className="learning-sq-question">{question.question_text}</p>
      {question.question_type === "mcq" &&
        Array.isArray(question.options) && (
          <ul className="question-options">
            {question.options.map((opt, i) => (
              <li
                key={i}
                className={`question-option ${showAnswer && question.correct_answer === String.fromCharCode(65 + i) ? "correct" : ""}`}
              >
                <span className="option-letter">
                  {String.fromCharCode(65 + i)}
                </span>
                <span className="option-text">{opt}</span>
              </li>
            ))}
          </ul>
        )}
      {showAnswer ? (
        <div className="learning-sq-answer">
          <p className="learning-sq-answer-label">
            Correct Answer: <strong>{question.correct_answer}</strong>
          </p>
          {question.explanation && (
            <p className="learning-sq-answer-text">{question.explanation}</p>
          )}
        </div>
      ) : (
        <button
          className="btn-secondary"
          style={{ fontSize: "0.8rem", padding: "6px 12px" }}
          onClick={() => setShowAnswer(true)}
        >
          Show Answer
        </button>
      )}
    </div>
  );
}

export function LearningOutputsPage() {
  const [learningData, setLearningData] = useState<MeetingLearningData[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [outputTypeFilter, setOutputTypeFilter] =
    useState<OutputType>("all");
  const [meetingFilter, setMeetingFilter] = useState<string>("all");
  const [offset, setOffset] = useState(0);
  const [meetings, setMeetings] = useState<MeetingListItem[]>([]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        setLoading(true);
        setError(null);
        const [meetingsRes, transcriptsRes] = await Promise.allSettled([
          getMeetings({ limit: 100 }),
          getTranscripts({ limit: 100, order_by: "created_at", order: "desc" }),
        ]);
        if (cancelled) return;

        const meetingsData =
          meetingsRes.status === "fulfilled" ? meetingsRes.value : null;
        const transcriptsData =
          transcriptsRes.status === "fulfilled" ? transcriptsRes.value : null;

        const meetingsList = meetingsData?.items ?? [];
        const transcriptsList = (transcriptsData?.items ?? []).filter(
          (t) => t.status === "completed" || t.status === "completed_with_warnings"
        );

        setMeetings(meetingsList);

        const meetingMap: Record<string, MeetingListItem> = {};
        meetingsList.forEach((m) => {
          meetingMap[m.id] = m;
        });

        const meetingTranscripts: Record<string, TranscriptListItem[]> = {};
        transcriptsList.forEach((t) => {
          if (!meetingTranscripts[t.meeting_id])
            meetingTranscripts[t.meeting_id] = [];
          meetingTranscripts[t.meeting_id].push(t);
        });

        const results: MeetingLearningData[] = [];

        for (const meetingId of Object.keys(meetingTranscripts)) {
          const meeting = meetingMap[meetingId];
          if (!meeting) continue;

          const transcripts = meetingTranscripts[meetingId];
          const firstTranscript = transcripts[0];

          const [fcRes, sqRes, countsRes, mcqsRes] = await Promise.allSettled([
            getLearningOutputs(firstTranscript.id, {
              output_type: "flashcard",
              offset: 0,
              limit: ITEM_PAGE_SIZE,
            }),
            getLearningOutputs(firstTranscript.id, {
              output_type: "short_question",
              offset: 0,
              limit: ITEM_PAGE_SIZE,
            }),
            getOutputCounts(firstTranscript.id),
            getTranscriptQuestions(firstTranscript.id, {
              question_type: "mcq",
              limit: 100,
            }),
          ]);
          if (cancelled) return;

          const flashcards =
            fcRes.status === "fulfilled" ? fcRes.value.items : [];
          const fcTotal =
            fcRes.status === "fulfilled" ? fcRes.value.total : 0;
          const shortQuestions =
            sqRes.status === "fulfilled" ? sqRes.value.items : [];
          const sqTotal =
            sqRes.status === "fulfilled" ? sqRes.value.total : 0;
          const counts =
            countsRes.status === "fulfilled" ? countsRes.value : null;
          const mcqs =
            mcqsRes.status === "fulfilled" ? mcqsRes.value : null;
          const mcqItems = mcqs?.items ?? [];

          const flashcardCount =
            counts?.counts.find((c) => c.output_type === "flashcard")?.count ??
            fcTotal;
          const sqCount =
            counts?.counts.find((c) => c.output_type === "short_question")
              ?.count ?? sqTotal;
          const mcqCount = mcqs?.total ?? mcqItems.length;

          const hasAny =
            flashcardCount > 0 || sqCount > 0 || mcqCount > 0;
          if (hasAny) {
            results.push({
              meeting,
              transcriptId: firstTranscript.id,
              flashcards,
              shortQuestions,
              mcqs: mcqItems,
              counts: counts?.counts ?? [],
              totalFlashcards: flashcardCount,
              totalShortQuestions: sqCount,
              totalMcqs: mcqCount,
              fcOffset: 0,
              sqOffset: 0,
              fcLoading: false,
              sqLoading: false,
            });
          }
        }

        if (!cancelled) {
          setLearningData(results);
          setLoading(false);
        }
      } catch (err) {
        if (!cancelled) {
          setError(
            err instanceof Error ? err.message : "Failed to load learning outputs"
          );
          setLoading(false);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const totalOutputs = learningData.reduce(
    (sum, d) => sum + d.totalFlashcards + d.totalShortQuestions + d.totalMcqs,
    0
  );
  const totalFlashcards = learningData.reduce(
    (sum, d) => sum + d.totalFlashcards,
    0
  );
  const totalShortQuestions = learningData.reduce(
    (sum, d) => sum + d.totalShortQuestions,
    0
  );
  const totalMcqs = learningData.reduce((sum, d) => sum + d.totalMcqs, 0);

  const filteredData = useMemo(() => {
    let list = learningData;
    if (search.trim()) {
      const q = search.toLowerCase();
      list = list.filter((d) => {
        const topicMatch = (d.meeting.topic ?? "").toLowerCase().includes(q);
        const fcMatch = d.flashcards.some(
          (f) =>
            ((f.content?.front as string) ?? "").toLowerCase().includes(q) ||
            ((f.content?.back as string) ?? "").toLowerCase().includes(q)
        );
        const sqMatch = d.shortQuestions.some(
          (sq) =>
            ((sq.content?.question_text as string) ?? "")
              .toLowerCase()
              .includes(q)
        );
        const mcqMatch = d.mcqs.some((mc) =>
          mc.question_text.toLowerCase().includes(q)
        );
        return topicMatch || fcMatch || sqMatch || mcqMatch;
      });
    }
    if (meetingFilter !== "all") {
      list = list.filter((d) => d.meeting.id === meetingFilter);
    }
    if (outputTypeFilter !== "all") {
      list = list.filter((d) => {
        if (outputTypeFilter === "flashcard") return d.totalFlashcards > 0;
        if (outputTypeFilter === "short_question")
          return d.totalShortQuestions > 0;
        if (outputTypeFilter === "mcq") return d.totalMcqs > 0;
        return true;
      });
    }
    return list;
  }, [learningData, search, meetingFilter, outputTypeFilter]);

  const pagedData = useMemo(() => {
    return filteredData.slice(offset, offset + PAGE_SIZE);
  }, [filteredData, offset]);

  const totalPages = Math.ceil(filteredData.length / PAGE_SIZE);
  const currentPage = Math.floor(offset / PAGE_SIZE) + 1;

  const meetingsWithOutputs = useMemo(() => {
    const ids = new Set<string>();
    learningData.forEach((d) => ids.add(d.meeting.id));
    return meetings.filter((m) => ids.has(m.id));
  }, [learningData, meetings]);

  const typeCounts = useMemo(() => {
    return {
      all: learningData.length,
      flashcard: learningData.filter((d) => d.totalFlashcards > 0).length,
      short_question: learningData.filter((d) => d.totalShortQuestions > 0)
        .length,
      mcq: learningData.filter((d) => d.totalMcqs > 0).length,
    };
  }, [learningData]);

  const updateMeetingData = useCallback(
    (meetingId: string, patch: Partial<MeetingLearningData>) => {
      setLearningData((prev) =>
        prev.map((d) =>
          d.meeting.id === meetingId ? { ...d, ...patch } : d
        )
      );
    },
    []
  );

  const loadFlashcardPage = useCallback(
    async (meetingId: string, transcriptId: string, newOffset: number) => {
      updateMeetingData(meetingId, { fcLoading: true });
      try {
        const res = await getLearningOutputs(transcriptId, {
          output_type: "flashcard",
          offset: newOffset,
          limit: ITEM_PAGE_SIZE,
        });
        updateMeetingData(meetingId, {
          flashcards: res.items,
          totalFlashcards: res.total,
          fcOffset: newOffset,
          fcLoading: false,
        });
      } catch {
        updateMeetingData(meetingId, { fcLoading: false });
      }
    },
    [updateMeetingData]
  );

  const loadShortQuestionPage = useCallback(
    async (meetingId: string, transcriptId: string, newOffset: number) => {
      updateMeetingData(meetingId, { sqLoading: true });
      try {
        const res = await getLearningOutputs(transcriptId, {
          output_type: "short_question",
          offset: newOffset,
          limit: ITEM_PAGE_SIZE,
        });
        updateMeetingData(meetingId, {
          shortQuestions: res.items,
          totalShortQuestions: res.total,
          sqOffset: newOffset,
          sqLoading: false,
        });
      } catch {
        updateMeetingData(meetingId, { sqLoading: false });
      }
    },
    [updateMeetingData]
  );

  return (
    <AppShell>
      <div className="learning-page">
        <div className="page-header">
          <h1>Learning Outputs</h1>
          <p className="page-header-subtitle">
            Flashcards, short questions, and MCQs generated from meeting
            transcripts
          </p>
        </div>

        {loading && <LoadingState message="Loading learning outputs..." />}
        {error && <ErrorState message={error} />}

        {!loading && !error && (
          <>
            <div className="learning-summary">
              <div className="learning-summary-card">
                <div className="learning-summary-icon learning-summary-icon-primary">
                  <Layers size={20} />
                </div>
                <div className="learning-summary-body">
                  <span className="learning-summary-value">
                    {totalOutputs}
                  </span>
                  <span className="learning-summary-label">Total Outputs</span>
                </div>
              </div>
              <div className="learning-summary-card">
                <div className="learning-summary-icon learning-summary-icon-success">
                  <BookOpen size={20} />
                </div>
                <div className="learning-summary-body">
                  <span className="learning-summary-value">
                    {totalFlashcards}
                  </span>
                  <span className="learning-summary-label">
                    Total Flashcards
                  </span>
                </div>
              </div>
              <div className="learning-summary-card">
                <div className="learning-summary-icon learning-summary-icon-warning">
                  <HelpCircle size={20} />
                </div>
                <div className="learning-summary-body">
                  <span className="learning-summary-value">
                    {totalShortQuestions}
                  </span>
                  <span className="learning-summary-label">
                    Total Short Questions
                  </span>
                </div>
              </div>
              <div className="learning-summary-card">
                <div className="learning-summary-icon learning-summary-icon-error">
                  <CheckSquare size={20} />
                </div>
                <div className="learning-summary-body">
                  <span className="learning-summary-value">{totalMcqs}</span>
                  <span className="learning-summary-label">Total MCQs</span>
                </div>
              </div>
            </div>

            <section className="panel learning-panel">
              <div className="learning-toolbar">
                <div className="learning-search-wrap">
                  <Search
                    size={16}
                    className="learning-search-icon"
                  />
                  <input
                    type="text"
                    className="learning-search-input"
                    placeholder="Search by topic, flashcard, question..."
                    value={search}
                    onChange={(e) => {
                      setSearch(e.target.value);
                      setOffset(0);
                    }}
                  />
                </div>
                <div className="learning-filters">
                  <Filter
                    size={14}
                    className="learning-filter-icon"
                  />
                  <select
                    className="filter-select"
                    value={outputTypeFilter}
                    onChange={(e) => {
                      setOutputTypeFilter(e.target.value as OutputType);
                      setOffset(0);
                    }}
                  >
                    <option value="all">
                      All Types ({typeCounts.all})
                    </option>
                    <option value="flashcard">
                      Flashcards ({typeCounts.flashcard})
                    </option>
                    <option value="short_question">
                      Short Questions ({typeCounts.short_question})
                    </option>
                    <option value="mcq">MCQs ({typeCounts.mcq})</option>
                  </select>
                  {meetingsWithOutputs.length > 0 && (
                    <select
                      className="filter-select"
                      value={meetingFilter}
                      onChange={(e) => {
                        setMeetingFilter(e.target.value);
                        setOffset(0);
                      }}
                    >
                      <option value="all">All Meetings</option>
                      {meetingsWithOutputs.map((m) => (
                        <option key={m.id} value={m.id}>
                          {m.topic ?? "Untitled Meeting"}
                        </option>
                      ))}
                    </select>
                  )}
                </div>
              </div>

              {pagedData.length > 0 ? (
                <div className="learning-list">
                  {pagedData.map((d) => (
                    <div key={d.meeting.id} className="learning-meeting-card">
                      <div className="learning-meeting-header">
                        <div className="learning-meeting-title-row">
                          <a
                            href={`#/meetings/${d.meeting.id}`}
                            className="learning-meeting-title"
                          >
                            {d.meeting.topic ?? "Untitled Meeting"}
                          </a>
                          <a
                            href={`#/meetings/${d.meeting.id}`}
                            className="learning-meeting-link"
                          >
                            <ExternalLink size={14} />
                            View Meeting
                          </a>
                        </div>
                        <div className="learning-meeting-meta">
                          <span className="learning-meta-item">
                            {formatRelativeTime(d.meeting.start_time)}
                          </span>
                          <span className="learning-meta-sep">&middot;</span>
                          <span className="learning-meta-item">
                            {d.totalFlashcards} flashcards
                          </span>
                          <span className="learning-meta-sep">&middot;</span>
                          <span className="learning-meta-item">
                            {d.totalShortQuestions} short questions
                          </span>
                          <span className="learning-meta-sep">&middot;</span>
                          <span className="learning-meta-item">
                            {d.totalMcqs} MCQs
                          </span>
                        </div>
                      </div>

                      {(outputTypeFilter === "all" ||
                        outputTypeFilter === "flashcard") &&
                        d.totalFlashcards > 0 && (
                          <div className="learning-section">
                            <h3 className="learning-section-title">
                              <BookOpen size={16} />
                              Flashcards
                              <span className="learning-section-count">{d.totalFlashcards}</span>
                              <span className="learning-section-hint" title="Click a card to flip it">
                                <RotateCcw
                                  size={12}
                                />
                              </span>
                            </h3>
                            {d.fcLoading ? (
                              <LoadingState message="Loading flashcards..." />
                            ) : (
                              <>
                                <div className="learning-flashcards-grid">
                                  {d.flashcards.map((fc, i) => (
                                    <FlashcardItem
                                      key={fc.id}
                                      item={fc}
                                      index={d.fcOffset + i}
                                    />
                                  ))}
                                </div>
                                {Math.ceil(d.totalFlashcards / ITEM_PAGE_SIZE) > 1 && (
                                  <div className="pagination">
                                    <button
                                      className="pagination-btn"
                                      disabled={d.fcOffset <= 0}
                                      onClick={() =>
                                        loadFlashcardPage(
                                          d.meeting.id,
                                          d.transcriptId,
                                          Math.max(0, d.fcOffset - ITEM_PAGE_SIZE)
                                        )
                                      }
                                    >
                                      <ChevronLeft size={14} />
                                      Previous
                                    </button>
                                    <span className="pagination-info">
                                      Page {Math.floor(d.fcOffset / ITEM_PAGE_SIZE) + 1} of {Math.ceil(d.totalFlashcards / ITEM_PAGE_SIZE)} ({d.totalFlashcards} flashcards)
                                    </span>
                                    <button
                                      className="pagination-btn"
                                      disabled={d.fcOffset + ITEM_PAGE_SIZE >= d.totalFlashcards}
                                      onClick={() =>
                                        loadFlashcardPage(
                                          d.meeting.id,
                                          d.transcriptId,
                                          d.fcOffset + ITEM_PAGE_SIZE
                                        )
                                      }
                                    >
                                      Next
                                      <ChevronRight size={14} />
                                    </button>
                                  </div>
                                )}
                              </>
                            )}
                          </div>
                        )}

                      {(outputTypeFilter === "all" ||
                        outputTypeFilter === "short_question") &&
                        d.totalShortQuestions > 0 && (
                          <div className="learning-section">
                            <h3 className="learning-section-title">
                              <HelpCircle size={16} />
                              Short Questions
                              <span className="learning-section-count">{d.totalShortQuestions}</span>
                            </h3>
                            {d.sqLoading ? (
                              <LoadingState message="Loading short questions..." />
                            ) : (
                              <>
                                <div className="learning-questions-list">
                                  {d.shortQuestions.map((sq, i) => (
                                    <ShortQuestionItem
                                      key={sq.id}
                                      item={sq}
                                      index={d.sqOffset + i}
                                    />
                                  ))}
                                </div>
                                {Math.ceil(d.totalShortQuestions / ITEM_PAGE_SIZE) > 1 && (
                                  <div className="pagination">
                                    <button
                                      className="pagination-btn"
                                      disabled={d.sqOffset <= 0}
                                      onClick={() =>
                                        loadShortQuestionPage(
                                          d.meeting.id,
                                          d.transcriptId,
                                          Math.max(0, d.sqOffset - ITEM_PAGE_SIZE)
                                        )
                                      }
                                    >
                                      <ChevronLeft size={14} />
                                      Previous
                                    </button>
                                    <span className="pagination-info">
                                      Page {Math.floor(d.sqOffset / ITEM_PAGE_SIZE) + 1} of {Math.ceil(d.totalShortQuestions / ITEM_PAGE_SIZE)} ({d.totalShortQuestions} questions)
                                    </span>
                                    <button
                                      className="pagination-btn"
                                      disabled={d.sqOffset + ITEM_PAGE_SIZE >= d.totalShortQuestions}
                                      onClick={() =>
                                        loadShortQuestionPage(
                                          d.meeting.id,
                                          d.transcriptId,
                                          d.sqOffset + ITEM_PAGE_SIZE
                                        )
                                      }
                                    >
                                      Next
                                      <ChevronRight size={14} />
                                    </button>
                                  </div>
                                )}
                              </>
                            )}
                          </div>
                        )}

                      {(outputTypeFilter === "all" ||
                        outputTypeFilter === "mcq") &&
                        d.totalMcqs > 0 && (
                          <div className="learning-section">
                            <h3 className="learning-section-title">
                              <CheckSquare size={16} />
                              Multiple Choice Questions
                            </h3>
                            <div className="learning-questions-list">
                              {d.mcqs.map((mc, i) => (
                                <McqItem
                                  key={mc.id}
                                  question={mc}
                                  index={i}
                                />
                              ))}
                            </div>
                          </div>
                        )}
                    </div>
                  ))}
                </div>
              ) : (
                <EmptyState
                  title="No Learning Outputs Found"
                  message={
                    search ||
                    meetingFilter !== "all" ||
                    outputTypeFilter !== "all"
                      ? "No outputs match your filters. Try adjusting your search."
                      : "No learning outputs generated yet. Process a meeting to generate flashcards and questions."
                  }
                />
              )}

              {totalPages > 1 && (
                <div className="pagination learning-pagination">
                  <button
                    className="pagination-btn"
                    disabled={currentPage <= 1}
                    onClick={() =>
                      setOffset(Math.max(0, offset - PAGE_SIZE))
                    }
                  >
                    <ChevronLeft size={16} />
                    Previous
                  </button>
                  <span className="pagination-info">
                    Page {currentPage} of {totalPages} &middot;{" "}
                    {filteredData.length} meetings
                  </span>
                  <button
                    className="pagination-btn"
                    disabled={currentPage >= totalPages}
                    onClick={() => setOffset(offset + PAGE_SIZE)}
                  >
                    Next
                    <ChevronRight size={16} />
                  </button>
                </div>
              )}
            </section>
          </>
        )}
      </div>
    </AppShell>
  );
}
