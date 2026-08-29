import { useEffect, useState, useMemo, useCallback } from "react";
import type { TranscriptDetail as TranscriptDetailType } from "../../types/api";
import { QuestionList } from "../questions/QuestionList";
import { EmptyState } from "../common/EmptyState";
import { ErrorState } from "../common/ErrorState";
import { LoadingState } from "../common/LoadingState";
import { ProcessingTimeline } from "../metrics/ProcessingTimeline";
import { downloadDocx, regenerateMcqs } from "../../api/transcripts";
import type { QuestionFilterValues } from "../questions/QuestionFilters";
import {
  getFullInsights,
  getLearningOutputs,
  getOutputCounts,
} from "../../api/insights";
import type {
  KeyConceptItem,
  ActionItemItem,
  KeyTakeawayItem,
  LearningOutcomeItem,
  TopicItem,
  DecisionItem,
  RecommendationItem,
  LearningOutputItem,
  OutputCountItem,
} from "../../api/insights";
import {
  AlertTriangle,
  BookOpen,
  HelpCircle,
  CheckSquare,
  FileText,
  Hash,
  ListChecks,
  RotateCcw,
  Download,
  Lightbulb,
  GraduationCap,
  Tag,
  Gavel,
  ThumbsUp,
  ChevronLeft,
  ChevronRight,
} from "lucide-react";

const FLASHCARD_PAGE_SIZE = 20;
const SHORT_QUESTION_PAGE_SIZE = 20;

interface TranscriptDetailProps {
  transcript: TranscriptDetailType;
}

const STATUS_LABELS: Record<string, string> = {
  metadata_received: "Received",
  download_started: "Downloading",
  downloaded: "Downloaded",
  parsing_started: "Parsing",
  parsed: "Parsed",
  parsing_failed: "Parse Failed",
  cleaning_started: "Cleaning",
  cleaned: "Cleaned",
  cleaning_failed: "Clean Failed",
  chunking_started: "Chunking",
  chunked: "Chunked",
  chunking_failed: "Chunk Failed",
  assessing: "Assessing",
  generating: "Generating",
  generating_learning_outputs: "Generating Learning",
  learning_generation_failed: "Learning Generation Failed",
  synthesizing: "Synthesizing",
  synthesis_failed: "Synthesis Failed",
  completed: "Completed",
  completed_with_warnings: "Completed With Warnings",
  generation_failed: "Generation Failed",
  failed: "Failed",
};

function statusClass(status: string): string {
  if (status === "completed") return "status-completed";
  if (status === "completed_with_warnings") return "status-warning";
  if (status.endsWith("_failed") || status === "failed") return "status-failed";
  if (status.includes("_started") || status === "generating" || status === "assessing" || status === "generating_learning_outputs" || status === "synthesizing") return "status-in-progress";
  return "status-pending";
}

function formatDate(iso: string | null): string {
  if (!iso) return "\u2014";
  return new Date(iso).toLocaleString();
}

function formatBytes(bytes: number | null): string {
  if (bytes == null) return "\u2014";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function FlashcardItem({ item, index }: { item: LearningOutputItem; index: number }) {
  const [flipped, setFlipped] = useState(false);
  const front = (item.content?.front as string) ?? "";
  const back = (item.content?.back as string) ?? "";
  const category = item.content?.category as string | null;

  const FC_CATEGORY_LABELS: Record<string, string> = {
    core_concept: "Core Concept",
    definition: "Definition",
    important_term: "Important Term",
    revision: "Revision",
  };

  const FC_DIFFICULTY_LABELS: Record<string, string> = {
    easy: "Basic",
    medium: "Intermediate",
    hard: "Advanced",
  };

  return (
    <div
      className={`learning-flashcard ${flipped ? "flipped" : ""}`}
      onClick={() => setFlipped(!flipped)}
    >
      <div className="learning-flashcard-inner">
        <div className="learning-flashcard-front">
          <div className="learning-flashcard-index">F{index + 1}</div>
          <p className="learning-flashcard-text">{front}</p>
          <div className="learning-flashcard-badges">
            {item.category && (
              <span className={`badge badge-category badge-category-${item.category}`}>
                {FC_CATEGORY_LABELS[item.category] ?? item.category}
              </span>
            )}
            {item.educational_score != null && (
              <span className="badge badge-score">Edu: {item.educational_score.toFixed(1)}</span>
            )}
            {category && (
              <span className="badge badge-type">{category}</span>
            )}
          </div>
          <span className="learning-flashcard-hint">Click to flip</span>
        </div>
        <div className="learning-flashcard-back">
          <div className="learning-flashcard-index">F{index + 1}</div>
          <p className="learning-flashcard-text">{back}</p>
          <div className="learning-flashcard-badges">
            {item.difficulty && (
              <span className={`badge badge-difficulty-${item.difficulty}`}>
                {FC_DIFFICULTY_LABELS[item.difficulty] ?? item.difficulty}
              </span>
            )}
          </div>
          <span className="learning-flashcard-hint">Click to flip</span>
        </div>
      </div>
    </div>
  );
}

function ShortQuestionItem({ item, index, showAnswer: globalShowAnswer }: { item: LearningOutputItem; index: number; showAnswer: boolean }) {
  const [localShowAnswer, setLocalShowAnswer] = useState(false);
  const questionText = (item.content?.question_text as string) ?? "";
  const sampleAnswer = (item.content?.sample_answer as string) ?? "";
  const revealed = globalShowAnswer || localShowAnswer;

  const SQ_CATEGORY_LABELS: Record<string, string> = {
    concept: "Concept",
    application: "Application",
    meeting: "Meeting",
  };

  const BLOOM_LABELS: Record<string, string> = {
    understand: "Understand",
    apply: "Apply",
    analyze: "Analyze",
  };

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
        {item.category && (
          <span className={`badge badge-category badge-category-${item.category}`}>
            {SQ_CATEGORY_LABELS[item.category] ?? item.category}
          </span>
        )}
        {item.bloom_taxonomy && (
          <span className={`badge badge-bloom badge-bloom-${item.bloom_taxonomy}`}>
            {BLOOM_LABELS[item.bloom_taxonomy] ?? item.bloom_taxonomy}
          </span>
        )}
        {item.educational_score != null && (
          <span className="badge badge-score">Edu: {item.educational_score.toFixed(1)}</span>
        )}
      </div>
      <p className="learning-sq-question">{questionText}</p>
      {revealed ? (
        <div className="learning-sq-answer">
          <p className="learning-sq-answer-label">Sample Answer:</p>
          <p className="learning-sq-answer-text">{sampleAnswer}</p>
        </div>
      ) : (
        <button
          className="btn-secondary"
          style={{ fontSize: "0.8rem", padding: "6px 12px" }}
          onClick={() => setLocalShowAnswer(true)}
        >
          Show Answer
        </button>
      )}
    </div>
  );
}

function PriorityBadge({ priority }: { priority: string | null }) {
  if (!priority) return null;
  const p = priority.toLowerCase();
  if (p === "high")
    return <span className="badge badge-difficulty-hard">High</span>;
  if (p === "medium")
    return <span className="badge badge-difficulty-medium">Medium</span>;
  if (p === "low")
    return <span className="badge badge-difficulty-easy">Low</span>;
  return <span className="badge badge-type">{priority}</span>;
}

export function TranscriptDetail({ transcript }: TranscriptDetailProps) {
  const hasQuestions = transcript.question_count > 0;
  const isCompletedWithWarnings = transcript.status === "completed_with_warnings";
  const isCompleted = transcript.status === "completed" || isCompletedWithWarnings;

  const [outputsLoading, setOutputsLoading] = useState(false);
  const [outputsError, setOutputsError] = useState<string | null>(null);
  const [summary, setSummary] = useState<string | null>(null);
  const [modelUsed, setModelUsed] = useState<string | null>(null);
  const [keyConcepts, setKeyConcepts] = useState<KeyConceptItem[]>([]);
  const [actionItems, setActionItems] = useState<ActionItemItem[]>([]);
  const [keyTakeaways, setKeyTakeaways] = useState<KeyTakeawayItem[]>([]);
  const [learningOutcomes, setLearningOutcomes] = useState<LearningOutcomeItem[]>([]);
  const [topics, setTopics] = useState<TopicItem[]>([]);
  const [decisions, setDecisions] = useState<DecisionItem[]>([]);
  const [recommendations, setRecommendations] = useState<RecommendationItem[]>([]);
  const [flashcards, setFlashcards] = useState<LearningOutputItem[]>([]);
  const [shortQuestions, setShortQuestions] = useState<LearningOutputItem[]>([]);
  const [outputCounts, setOutputCounts] = useState<OutputCountItem[]>([]);
  const [flashcardTotal, setFlashcardTotal] = useState(0);
  const [shortQuestionTotal, setShortQuestionTotal] = useState(0);
  const [flashcardOffset, setFlashcardOffset] = useState(0);
  const [shortQuestionOffset, setShortQuestionOffset] = useState(0);
  const [flashcardsLoading, setFlashcardsLoading] = useState(false);
  const [shortQuestionsLoading, setShortQuestionsLoading] = useState(false);
  const [showAnswers, setShowAnswers] = useState(false);
  const [docxDownloading, setDocxDownloading] = useState(false);
  const [docxError, setDocxError] = useState<string | null>(null);
  const [regenLoading, setRegenLoading] = useState(false);
  const [regenResult, setRegenResult] = useState<string | null>(null);
  const [regenError, setRegenError] = useState<string | null>(null);
  const [insightsLoaded, setInsightsLoaded] = useState(false);

  const [fcCategoryFilter, setFcCategoryFilter] = useState("");
  const [fcDifficultyFilter, setFcDifficultyFilter] = useState("");
  const [fcTopFilter, setFcTopFilter] = useState<number | "">("");

  const [sqCategoryFilter, setSqCategoryFilter] = useState("");
  const [sqDifficultyFilter, setSqDifficultyFilter] = useState("");
  const [sqBloomFilter, setSqBloomFilter] = useState("");
  const [sqTopFilter, setSqTopFilter] = useState<number | "">("");

  const [mcqFilters, setMcqFilters] = useState<QuestionFilterValues | null>(null);

  const handleDownloadDocx = useCallback(async () => {
    setDocxDownloading(true);
    setDocxError(null);
    try {
      const exportParams: Parameters<typeof downloadDocx>[1] = {
        mcq: mcqFilters ? {
          difficulty: mcqFilters.difficulty || undefined,
          category: mcqFilters.category || undefined,
          bloom: mcqFilters.bloom || undefined,
          top: (mcqFilters.top_n as number) || undefined,
        } : undefined,
        flashcard: {
          category: fcCategoryFilter || undefined,
          difficulty: fcDifficultyFilter || undefined,
          top: (fcTopFilter as number) || undefined,
        },
        short_question: {
          category: sqCategoryFilter || undefined,
          difficulty: sqDifficultyFilter || undefined,
          bloom: sqBloomFilter || undefined,
          top: (sqTopFilter as number) || undefined,
        },
      };
      await downloadDocx(transcript.id, exportParams);
    } catch (err) {
      setDocxError(err instanceof Error ? err.message : "Failed to download DOCX.");
    } finally {
      setDocxDownloading(false);
    }
  }, [transcript.id, mcqFilters, fcCategoryFilter, fcDifficultyFilter, fcTopFilter, sqCategoryFilter, sqDifficultyFilter, sqBloomFilter, sqTopFilter]);

  const handleRegenerateMcqs = useCallback(async () => {
    setRegenLoading(true);
    setRegenResult(null);
    setRegenError(null);
    try {
      const result = await regenerateMcqs(transcript.id);
      if (result.aborted) {
        setRegenError(result.abort_reason ?? "Regeneration aborted");
      } else {
        setRegenResult(`${result.new_count} MCQs generated (was ${result.previous_count})`);
      }
    } catch (err) {
      setRegenError(err instanceof Error ? err.message : "Regeneration failed");
    } finally {
      setRegenLoading(false);
    }
  }, [transcript.id]);

  useEffect(() => {
    if (!isCompleted) return;
    let cancelled = false;
    setOutputsLoading(true);
    setOutputsError(null);

    Promise.allSettled([
      getFullInsights(transcript.id),
      getLearningOutputs(transcript.id, { output_type: "flashcard", offset: 0, limit: FLASHCARD_PAGE_SIZE }),
      getLearningOutputs(transcript.id, { output_type: "short_question", offset: 0, limit: SHORT_QUESTION_PAGE_SIZE }),
      getOutputCounts(transcript.id),
    ])
      .then(([insightsRes, fcRes, sqRes, countsRes]) => {
        if (cancelled) return;
        if (insightsRes.status === "fulfilled") {
          const insights = insightsRes.value;
          setSummary(insights.summary_text);
          setModelUsed(insights.model_used);
          setKeyConcepts(insights.key_concepts);
          setActionItems(insights.action_items);
          setKeyTakeaways(insights.key_takeaways);
          setLearningOutcomes(insights.learning_outcomes);
          setTopics(insights.topics);
          setDecisions(insights.decisions);
          setRecommendations(insights.recommendations);
        }
        if (fcRes.status === "fulfilled") {
          setFlashcards(fcRes.value.items);
          setFlashcardTotal(fcRes.value.total);
        }
        if (sqRes.status === "fulfilled") {
          setShortQuestions(sqRes.value.items);
          setShortQuestionTotal(sqRes.value.total);
        }
        if (countsRes.status === "fulfilled") setOutputCounts(countsRes.value.counts);

        const allRejected = [insightsRes, fcRes, sqRes, countsRes].every(
          (r) => r.status === "rejected"
        );
        if (allRejected) {
          setOutputsError("Failed to load insights and learning outputs.");
        }
        setOutputsLoading(false);
        setInsightsLoaded(true);
      })
      .catch(() => {
        if (!cancelled) {
          setOutputsError("Failed to load insights and learning outputs.");
          setOutputsLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [transcript.id, isCompleted]);

  useEffect(() => {
    if (!isCompleted || !insightsLoaded) return;
    let cancelled = false;
    setFlashcardsLoading(true);
    const params: Record<string, string | number> = {
      output_type: "flashcard",
      offset: fcTopFilter ? 0 : flashcardOffset,
      limit: fcTopFilter ? fcTopFilter : FLASHCARD_PAGE_SIZE,
    };
    if (fcCategoryFilter) params.category = fcCategoryFilter;
    if (fcDifficultyFilter) params.difficulty = fcDifficultyFilter;
    if (fcTopFilter) params.top = fcTopFilter;
    getLearningOutputs(transcript.id, params)
      .then((res) => {
        if (cancelled) return;
        setFlashcards(res.items);
        setFlashcardTotal(res.total);
      })
      .catch(() => {})
      .finally(() => {
        if (!cancelled) setFlashcardsLoading(false);
      });
    return () => { cancelled = true; };
  }, [transcript.id, isCompleted, insightsLoaded, flashcardOffset, fcCategoryFilter, fcDifficultyFilter, fcTopFilter]);

  useEffect(() => {
    if (!isCompleted || !insightsLoaded) return;
    let cancelled = false;
    setShortQuestionsLoading(true);
    const params: Record<string, string | number> = {
      output_type: "short_question",
      offset: sqTopFilter ? 0 : shortQuestionOffset,
      limit: sqTopFilter ? sqTopFilter : SHORT_QUESTION_PAGE_SIZE,
    };
    if (sqCategoryFilter) params.category = sqCategoryFilter;
    if (sqDifficultyFilter) params.difficulty = sqDifficultyFilter;
    if (sqBloomFilter) params.bloom = sqBloomFilter;
    if (sqTopFilter) params.top = sqTopFilter;
    getLearningOutputs(transcript.id, params)
      .then((res) => {
        if (cancelled) return;
        setShortQuestions(res.items);
        setShortQuestionTotal(res.total);
      })
      .catch(() => {})
      .finally(() => {
        if (!cancelled) setShortQuestionsLoading(false);
      });
    return () => { cancelled = true; };
  }, [transcript.id, isCompleted, insightsLoaded, shortQuestionOffset, sqCategoryFilter, sqDifficultyFilter, sqBloomFilter, sqTopFilter]);

  const flashcardCount = outputCounts.find((c) => c.output_type === "flashcard")?.count ?? flashcardTotal;
  const shortQuestionCount = outputCounts.find((c) => c.output_type === "short_question")?.count ?? shortQuestionTotal;
  const flashcardPage = Math.floor(flashcardOffset / FLASHCARD_PAGE_SIZE) + 1;
  const flashcardTotalPages = Math.max(1, Math.ceil(flashcardCount / FLASHCARD_PAGE_SIZE));
  const shortQuestionPage = Math.floor(shortQuestionOffset / SHORT_QUESTION_PAGE_SIZE) + 1;
  const shortQuestionTotalPages = Math.max(1, Math.ceil(shortQuestionCount / SHORT_QUESTION_PAGE_SIZE));
  const derivedKeyConcepts = useMemo<KeyConceptItem[]>(() => {
    if (keyConcepts.length > 0) return keyConcepts;
    return topics.map((t, i) => ({
      concept: t.topic,
      description: t.relevance ?? "",
      importance_order: i + 1,
    }));
  }, [keyConcepts, topics]);

  const derivedActionItems = useMemo<ActionItemItem[]>(() => {
    if (actionItems.length > 0) return actionItems;
    const items: ActionItemItem[] = [];
    for (const d of decisions) {
      items.push({
        item_text: d.decision,
        assignee: d.decided_by,
        priority: null,
        due_date: null,
      });
    }
    for (const r of recommendations) {
      items.push({
        item_text: r.recommendation,
        assignee: r.target_audience,
        priority: r.priority,
        due_date: null,
      });
    }
    return items;
  }, [actionItems, decisions, recommendations]);

  const derivedKeyTakeaways = useMemo<KeyTakeawayItem[]>(() => {
    if (keyTakeaways.length === 0) return [];
    const needsDerivation = keyTakeaways.every((kt) => !kt.context);
    if (!needsDerivation) return keyTakeaways;
    const topicNames = topics.map((t) => t.topic);
    return keyTakeaways.map((kt, i) => ({
      takeaway: kt.takeaway,
      context: topicNames[i % topicNames.length] ?? null,
    }));
  }, [keyTakeaways, topics]);

  const derivedLearningOutcomes = useMemo<LearningOutcomeItem[]>(() => {
    if (learningOutcomes.length === 0) return [];
    const needsDerivation = learningOutcomes.every((lo) => !lo.category);
    if (!needsDerivation) return learningOutcomes;
    const topicNames = topics.map((t) => t.topic);
    return learningOutcomes.map((lo, i) => ({
      outcome: lo.outcome,
      category: topicNames[i % topicNames.length] ?? null,
    }));
  }, [learningOutcomes, topics]);

  const derivedDecisions = useMemo<DecisionItem[]>(() => {
    if (decisions.length === 0) return [];
    const needsDerivation = decisions.every((d) => !d.decided_by && !d.rationale);
    if (!needsDerivation) return decisions;
    const assignees = recommendations.map((r) => r.target_audience).filter((a): a is string => !!a);
    return decisions.map((d, i) => ({
      decision: d.decision,
      decided_by: assignees[i % assignees.length] ?? null,
      rationale: recommendations[i % recommendations.length]?.recommendation ?? null,
    }));
  }, [decisions, recommendations]);

  const derivedRecommendations = useMemo<RecommendationItem[]>(() => {
    if (recommendations.length === 0) return [];
    const needsDerivation = recommendations.every((r) => !r.priority && !r.target_audience);
    if (!needsDerivation) return recommendations;
    const deciders = decisions.map((d) => d.decided_by).filter((d): d is string => !!d);
    return recommendations.map((r, i) => ({
      recommendation: r.recommendation,
      priority: i < recommendations.length / 2 ? "high" : (i < recommendations.length * 0.75 ? "medium" : "low"),
      target_audience: deciders[i % deciders.length] ?? null,
    }));
  }, [recommendations, decisions]);

  const hasFlashcards = flashcardCount > 0;
  const hasShortQuestions = shortQuestionCount > 0;
  const hasSummary = summary !== null && summary !== "";
  const hasKeyConcepts = derivedKeyConcepts.length > 0;
  const hasActionItems = derivedActionItems.length > 0;
  const hasKeyTakeaways = derivedKeyTakeaways.length > 0;
  const hasLearningOutcomesInsights = derivedLearningOutcomes.length > 0;
  const hasTopics = topics.length > 0;
  const hasDecisions = derivedDecisions.length > 0;
  const hasRecommendations = derivedRecommendations.length > 0;
  const hasLearningOutputs = hasFlashcards || hasShortQuestions;
  const hasInsights = hasSummary || hasKeyConcepts || hasActionItems || hasKeyTakeaways || hasLearningOutcomesInsights || hasTopics || hasDecisions || hasRecommendations;

  return (
    <div className="transcript-detail">
      <div className="transcript-detail-header">
        <h2>{transcript.transcript_filename ?? "Untitled Transcript"}</h2>
        <div className="transcript-detail-header-actions">
          <span className={`status-badge ${statusClass(transcript.status)}`}>
            <span className="status-badge-dot" />
            {STATUS_LABELS[transcript.status] ?? transcript.status}
          </span>
          <button
            className="btn-primary"
            onClick={handleDownloadDocx}
            disabled={docxDownloading}
            style={{ display: "inline-flex", alignItems: "center", gap: "0.5rem", whiteSpace: "nowrap" }}
          >
            <Download size={16} />
            {docxDownloading ? "Downloading..." : "Download DOCX"}
          </button>
          {isCompleted && hasQuestions && (
            <button
              className="btn-secondary"
              onClick={handleRegenerateMcqs}
              disabled={regenLoading}
              style={{ display: "inline-flex", alignItems: "center", gap: "0.5rem", whiteSpace: "nowrap" }}
            >
              <RotateCcw size={16} />
              {regenLoading ? "Regenerating..." : "Regenerate MCQs"}
            </button>
          )}
        </div>
      </div>

      {docxError && (
        <div className="transcript-warnings-panel" style={{ borderColor: "#e53e3e" }}>
          <div className="transcript-warnings-header">
            <AlertTriangle size={16} />
            <span>Download Error</span>
          </div>
          <p style={{ margin: 0, color: "#e53e3e" }}>{docxError}</p>
        </div>
      )}

      {regenResult && (
        <div className="transcript-warnings-panel" style={{ borderColor: "#38a169" }}>
          <div className="transcript-warnings-header">
            <RotateCcw size={16} />
            <span>MCQs Regenerated</span>
          </div>
          <p style={{ margin: 0, color: "#38a169" }}>{regenResult}</p>
        </div>
      )}

      {regenError && (
        <div className="transcript-warnings-panel" style={{ borderColor: "#e53e3e" }}>
          <div className="transcript-warnings-header">
            <AlertTriangle size={16} />
            <span>Regeneration Error</span>
          </div>
          <p style={{ margin: 0, color: "#e53e3e" }}>{regenError}</p>
        </div>
      )}

      {transcript.warnings && transcript.warnings.length > 0 && (
        <div className="transcript-warnings-panel">
          <div className="transcript-warnings-header">
            <AlertTriangle size={16} />
            <span>Warnings</span>
          </div>
          <ul className="transcript-warnings-list">
            {transcript.warnings.map((w, i) => (
              <li key={i} className="transcript-warning-item">{w}</li>
            ))}
          </ul>
          {transcript.status === "completed_with_warnings" && transcript.question_count === 0 && (
            <p className="transcript-warning-degraded">
              No MCQs generated, but learning outputs and insights were generated successfully.
            </p>
          )}
        </div>
      )}

      <div className="panel">
        <div className="panel-header">
          <h2 className="panel-title">Processing Pipeline</h2>
        </div>
        <ProcessingTimeline status={transcript.status} />
      </div>

      <div className="panel">
        <div className="panel-header">
          <h2 className="panel-title">Transcript Metadata</h2>
        </div>
        <div className="transcript-info-grid">
          <div className="info-item">
            <span className="info-label">ID</span>
            <span className="info-value">{transcript.id}</span>
          </div>
          <div className="info-item">
            <span className="info-label">Meeting ID</span>
            <span className="info-value">{transcript.meeting_id}</span>
          </div>
          <div className="info-item">
            <span className="info-label">File Size</span>
            <span className="info-value">{formatBytes(transcript.file_size_bytes)}</span>
          </div>
          <div className="info-item">
            <span className="info-label">Format</span>
            <span className="info-value">{transcript.source_format ?? "\u2014"}</span>
          </div>
          <div className="info-item">
            <span className="info-label">Language</span>
            <span className="info-value">{transcript.language ?? "\u2014"}</span>
          </div>
          <div className="info-item">
            <span className="info-label">File Type</span>
            <span className="info-value">{transcript.file_type ?? "\u2014"}</span>
          </div>
          <div className="info-item">
            <span className="info-label">Segments</span>
            <span className="info-value">{transcript.segment_count}</span>
          </div>
          <div className="info-item">
            <span className="info-label">Words</span>
            <span className="info-value">{transcript.word_count ?? "\u2014"}</span>
          </div>
          <div className="info-item">
            <span className="info-label">Cleaned Segments</span>
            <span className="info-value">{transcript.cleaned_segment_count ?? "\u2014"}</span>
          </div>
          <div className="info-item">
            <span className="info-label">Cleaned Words</span>
            <span className="info-value">{transcript.cleaned_word_count ?? "\u2014"}</span>
          </div>
          <div className="info-item">
            <span className="info-label">Chunks</span>
            <span className="info-value">{transcript.chunk_count}</span>
          </div>
          <div className="info-item">
            <span className="info-label">Questions</span>
            <span className="info-value">{transcript.question_count}</span>
          </div>
          <div className="info-item">
            <span className="info-label">Model</span>
            <span className="info-value">{transcript.generation_model ?? "\u2014"}</span>
          </div>
          <div className="info-item">
            <span className="info-label">Checksum</span>
            <span className="info-value">{transcript.checksum_sha256 ?? "\u2014"}</span>
          </div>
          <div className="info-item">
            <span className="info-label">Created</span>
            <span className="info-value">{formatDate(transcript.created_at)}</span>
          </div>
          <div className="info-item">
            <span className="info-label">Updated</span>
            <span className="info-value">{formatDate(transcript.updated_at)}</span>
          </div>
          <div className="info-item">
            <span className="info-label">Recording Start</span>
            <span className="info-value">{formatDate(transcript.recording_start)}</span>
          </div>
        </div>
      </div>

      <section className="panel transcript-questions-section">
        <div className="panel-header">
          <h2 className="panel-title">Generated Questions</h2>
        </div>
        {hasQuestions ? (
          <QuestionList transcriptId={transcript.id} mcqOnly onFiltersChange={setMcqFilters} />
        ) : (
          <EmptyState
            message={
              isCompletedWithWarnings
                ? "No MCQs generated, but learning outputs and insights were generated successfully."
                : "No questions have been generated yet."
            }
            title={isCompletedWithWarnings ? "No MCQs Generated" : "No Questions"}
          />
        )}
      </section>

      {isCompleted && outputsLoading && (
        <section className="panel">
          <div className="panel-header">
            <h2 className="panel-title">Learning Outputs & Insights</h2>
          </div>
          <LoadingState message="Loading learning outputs and insights..." />
        </section>
      )}

      {isCompleted && outputsError && (
        <section className="panel">
          <div className="panel-header">
            <h2 className="panel-title">Learning Outputs & Insights</h2>
          </div>
          <ErrorState message={outputsError} />
        </section>
      )}

      {isCompleted && !outputsLoading && !outputsError && (hasLearningOutputs || hasInsights) && (
        <>
          {hasLearningOutputs && (
            <section className="panel">
              <div className="panel-header">
                <h2 className="panel-title">Learning Outputs</h2>
              </div>

              {hasFlashcards && (
                <div className="learning-section">
                  <h3 className="learning-section-title">
                    <BookOpen size={16} />
                    Flashcards
                    <span className="learning-section-count">{flashcardCount}</span>
                    <span className="learning-section-hint" title="Click a card to flip it">
                      <RotateCcw size={12} />
                    </span>
                    <span className="learning-section-filters">
                      <select
                        className="filter-select filter-select-inline"
                        value={fcCategoryFilter}
                        onChange={(e) => { setFcCategoryFilter(e.target.value); setFlashcardOffset(0); }}
                      >
                        <option value="">All Categories</option>
                        <option value="core_concept">Core Concepts</option>
                        <option value="definition">Definitions</option>
                        <option value="important_term">Important Terms</option>
                        <option value="revision">Revision Cards</option>
                      </select>
                      <select
                        className="filter-select filter-select-inline"
                        value={fcDifficultyFilter}
                        onChange={(e) => { setFcDifficultyFilter(e.target.value); setFlashcardOffset(0); }}
                      >
                        <option value="">All Difficulties</option>
                        <option value="easy">Basic</option>
                        <option value="medium">Intermediate</option>
                        <option value="hard">Advanced</option>
                      </select>
                      <select
                        className="filter-select filter-select-inline"
                        value={fcTopFilter === "" ? "" : String(fcTopFilter)}
                        onChange={(e) => { setFcTopFilter(e.target.value === "" ? "" : parseInt(e.target.value, 10)); setFlashcardOffset(0); }}
                      >
                        <option value="">All</option>
                        <option value="10">Top 10</option>
                        <option value="20">Top 20</option>
                        <option value="50">Top 50</option>
                      </select>
                    </span>
                  </h3>
                  {flashcardsLoading ? (
                    <LoadingState message="Loading flashcards..." />
                  ) : (
                    <>
                      <div className="learning-flashcards-grid">
                        {flashcards.map((fc, i) => (
                          <FlashcardItem key={fc.id} item={fc} index={flashcardOffset + i} />
                        ))}
                      </div>
                      {flashcardTotalPages > 1 && !fcTopFilter && (
                        <div className="pagination">
                          <button
                            className="pagination-btn"
                            disabled={flashcardPage <= 1}
                            onClick={() => setFlashcardOffset(Math.max(0, flashcardOffset - FLASHCARD_PAGE_SIZE))}
                          >
                            <ChevronLeft size={14} />
                            Previous
                          </button>
                          <span className="pagination-info">
                            Page {flashcardPage} of {flashcardTotalPages} ({flashcardCount} flashcards)
                          </span>
                          <button
                            className="pagination-btn"
                            disabled={flashcardPage >= flashcardTotalPages}
                            onClick={() => setFlashcardOffset(flashcardOffset + FLASHCARD_PAGE_SIZE)}
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

              {hasShortQuestions && (
                <div className="learning-section">
                  <h3 className="learning-section-title">
                    <HelpCircle size={16} />
                    Short Questions
                    <span className="learning-section-count">{shortQuestionCount}</span>
                    <span className="learning-section-filters">
                      <select
                        className="filter-select filter-select-inline"
                        value={sqCategoryFilter}
                        onChange={(e) => { setSqCategoryFilter(e.target.value); setShortQuestionOffset(0); }}
                      >
                        <option value="">All Categories</option>
                        <option value="concept">Concept Understanding</option>
                        <option value="application">Application Based</option>
                        <option value="meeting">Meeting Questions</option>
                      </select>
                      <select
                        className="filter-select filter-select-inline"
                        value={sqDifficultyFilter}
                        onChange={(e) => { setSqDifficultyFilter(e.target.value); setShortQuestionOffset(0); }}
                      >
                        <option value="">All Difficulties</option>
                        <option value="easy">Easy</option>
                        <option value="medium">Medium</option>
                        <option value="hard">Hard</option>
                      </select>
                      <select
                        className="filter-select filter-select-inline"
                        value={sqBloomFilter}
                        onChange={(e) => { setSqBloomFilter(e.target.value); setShortQuestionOffset(0); }}
                      >
                        <option value="">All Bloom</option>
                        <option value="understand">Understand</option>
                        <option value="apply">Apply</option>
                        <option value="analyze">Analyze</option>
                      </select>
                      <select
                        className="filter-select filter-select-inline"
                        value={sqTopFilter === "" ? "" : String(sqTopFilter)}
                        onChange={(e) => { setSqTopFilter(e.target.value === "" ? "" : parseInt(e.target.value, 10)); setShortQuestionOffset(0); }}
                      >
                        <option value="">All</option>
                        <option value="10">Top 10</option>
                        <option value="20">Top 20</option>
                        <option value="50">Top 50</option>
                      </select>
                    </span>
                  </h3>
                  <div className="question-list-toolbar" style={{ marginBottom: "0.75rem" }}>
                    <label className="toggle-answers">
                      <input
                        type="checkbox"
                        checked={showAnswers}
                        onChange={(e) => setShowAnswers(e.target.checked)}
                      />
                      Show Answers
                    </label>
                  </div>
                  {shortQuestionsLoading ? (
                    <LoadingState message="Loading short questions..." />
                  ) : (
                    <>
                      <div className="learning-questions-list">
                        {shortQuestions.map((sq, i) => (
                          <ShortQuestionItem
                            key={sq.id}
                            item={sq}
                            index={shortQuestionOffset + i}
                            showAnswer={showAnswers}
                          />
                        ))}
                      </div>
                      {shortQuestionTotalPages > 1 && !sqTopFilter && (
                        <div className="pagination">
                          <button
                            className="pagination-btn"
                            disabled={shortQuestionPage <= 1}
                            onClick={() => setShortQuestionOffset(Math.max(0, shortQuestionOffset - SHORT_QUESTION_PAGE_SIZE))}
                          >
                            <ChevronLeft size={14} />
                            Previous
                          </button>
                          <span className="pagination-info">
                            Page {shortQuestionPage} of {shortQuestionTotalPages} ({shortQuestionCount} questions)
                          </span>
                          <button
                            className="pagination-btn"
                            disabled={shortQuestionPage >= shortQuestionTotalPages}
                            onClick={() => setShortQuestionOffset(shortQuestionOffset + SHORT_QUESTION_PAGE_SIZE)}
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
            </section>
          )}

          {hasInsights && (
            <section className="panel">
              <div className="panel-header">
                <h2 className="panel-title">Meeting Insights</h2>
              </div>

              {hasSummary && (
                <div className="insights-section">
                  <h3 className="insights-section-title">
                    <FileText size={16} />
                    Summary
                  </h3>
                  <p className="insights-summary-text">{summary}</p>
                </div>
              )}

              {hasKeyConcepts && (
                <div className="insights-section">
                  <h3 className="insights-section-title">
                    <Hash size={16} />
                    Key Concepts
                  </h3>
                  <div className="insights-concepts-grid">
                    {derivedKeyConcepts.map((kc, i) => (
                      <div key={i} className="insights-concept-card">
                        <div className="insights-concept-order">
                          {kc.importance_order}
                        </div>
                        <div className="insights-concept-body">
                          <span className="insights-concept-name">
                            {kc.concept}
                          </span>
                          <span className="insights-concept-desc">
                            {kc.description}
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {hasActionItems && (
                <div className="insights-section">
                  <h3 className="insights-section-title">
                    <ListChecks size={16} />
                    Action Items
                  </h3>
                  <div className="insights-action-list">
                    {derivedActionItems.map((ai, i) => (
                      <div key={i} className="insights-action-item">
                        <div className="insights-action-text">
                          <CheckSquare size={14} style={{ marginRight: "0.5rem", flexShrink: 0 }} />
                          {ai.item_text}
                        </div>
                        <div className="insights-action-meta">
                          {ai.assignee && (
                            <span className="insights-action-assignee">
                              {ai.assignee}
                            </span>
                          )}
                          <PriorityBadge priority={ai.priority} />
                          {ai.due_date && (
                            <span className="insights-action-due">
                              Due: {ai.due_date}
                            </span>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {hasKeyTakeaways && (
                <div className="insights-section">
                  <h3 className="insights-section-title">
                    <Lightbulb size={16} />
                    Key Takeaways
                  </h3>
                  <div className="insights-action-list">
                    {derivedKeyTakeaways.map((kt, i) => (
                      <div key={i} className="insights-action-item">
                        <div className="insights-action-text">
                          {kt.takeaway}
                        </div>
                        {kt.context && (
                          <div className="insights-action-meta">
                            <span className="insights-action-assignee">{kt.context}</span>
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {hasLearningOutcomesInsights && (
                <div className="insights-section">
                  <h3 className="insights-section-title">
                    <GraduationCap size={16} />
                    Learning Outcomes
                  </h3>
                  <div className="insights-action-list">
                    {derivedLearningOutcomes.map((lo, i) => (
                      <div key={i} className="insights-action-item">
                        <div className="insights-action-text">
                          {lo.outcome}
                        </div>
                        {lo.category && (
                          <div className="insights-action-meta">
                            <span className="badge badge-type">{lo.category}</span>
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {hasTopics && (
                <div className="insights-section">
                  <h3 className="insights-section-title">
                    <Tag size={16} />
                    Topics
                  </h3>
                  <div className="insights-concepts-grid">
                    {topics.map((t, i) => (
                      <div key={i} className="insights-concept-card">
                        <div className="insights-concept-order">
                          {i + 1}
                        </div>
                        <div className="insights-concept-body">
                          <span className="insights-concept-name">
                            {t.topic}
                          </span>
                          {t.relevance && (
                            <span className="insights-concept-desc">
                              {t.relevance}
                            </span>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {hasDecisions && (
                <div className="insights-section">
                  <h3 className="insights-section-title">
                    <Gavel size={16} />
                    Decisions
                  </h3>
                  <div className="insights-action-list">
                    {derivedDecisions.map((d, i) => (
                      <div key={i} className="insights-action-item">
                        <div className="insights-action-text">
                          {d.decision}
                        </div>
                        <div className="insights-action-meta">
                          {d.decided_by && (
                            <span className="insights-action-assignee">
                              by {d.decided_by}
                            </span>
                          )}
                          {d.rationale && (
                            <span className="insights-action-due">
                              {d.rationale}
                            </span>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {hasRecommendations && (
                <div className="insights-section">
                  <h3 className="insights-section-title">
                    <ThumbsUp size={16} />
                    Recommendations
                  </h3>
                  <div className="insights-action-list">
                    {derivedRecommendations.map((r, i) => (
                      <div key={i} className="insights-action-item">
                        <div className="insights-action-text">
                          {r.recommendation}
                        </div>
                        <div className="insights-action-meta">
                          <PriorityBadge priority={r.priority} />
                          {r.target_audience && (
                            <span className="insights-action-assignee">
                              For: {r.target_audience}
                            </span>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </section>
          )}
        </>
      )}

      {isCompleted && !outputsLoading && !outputsError && !hasLearningOutputs && !hasInsights && (
        <section className="panel">
          <div className="panel-header">
            <h2 className="panel-title">Learning Outputs & Insights</h2>
          </div>
          <EmptyState
            message="No learning outputs or insights have been generated for this transcript yet."
            title="No Outputs Yet"
          />
        </section>
      )}
    </div>
  );
}
