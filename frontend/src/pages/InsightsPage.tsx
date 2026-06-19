import { useEffect, useState, useMemo } from "react";
import {
  Lightbulb,
  FileText,
  Hash,
  ListChecks,
  Search,
  Filter,
  ChevronLeft,
  ChevronRight,
  ExternalLink,
  AlertCircle,
  BookOpen,
  GraduationCap,
  Tag,
  Gavel,
  ThumbsUp,
} from "lucide-react";
import { AppShell } from "../components/layout/AppShell";
import { LoadingState } from "../components/common/LoadingState";
import { ErrorState } from "../components/common/ErrorState";
import { EmptyState } from "../components/common/EmptyState";
import { getMeetings } from "../api/meetings";
import { getTranscripts } from "../api/transcripts";
import {
  getSummary,
  getKeyConcepts,
  getActionItems,
  getKeyTakeaways,
  getLearningOutcomes,
  getTopics,
  getDecisions,
  getRecommendations,
} from "../api/insights";
import type { MeetingListItem, TranscriptListItem } from "../types/api";
import type {
  SummaryResponse,
  KeyConceptItem,
  ActionItemItem,
  KeyTakeawayItem,
  LearningOutcomeItem,
  TopicItem,
  DecisionItem,
  RecommendationItem,
} from "../api/insights";

const PAGE_SIZE = 10;

type Section =
  | "all"
  | "summary"
  | "key_concepts"
  | "action_items"
  | "key_takeaways"
  | "learning_outcomes"
  | "topics"
  | "decisions"
  | "recommendations";

interface TranscriptWithInsights {
  transcript: TranscriptListItem;
  meeting: MeetingListItem;
  summary: SummaryResponse | null;
  keyConcepts: KeyConceptItem[];
  actionItems: ActionItemItem[];
  keyTakeaways: KeyTakeawayItem[];
  learningOutcomes: LearningOutcomeItem[];
  topics: TopicItem[];
  decisions: DecisionItem[];
  recommendations: RecommendationItem[];
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

export function InsightsPage() {
  const [insightsData, setInsightsData] = useState<TranscriptWithInsights[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [sectionFilter, setSectionFilter] = useState<Section>("all");
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

        const results: TranscriptWithInsights[] = [];
        for (const t of transcriptsList) {
          const meeting = meetingMap[t.meeting_id];
          if (!meeting) continue;
          const [
            summaryRes,
            conceptsRes,
            actionsRes,
            takeawaysRes,
            outcomesRes,
            topicsRes,
            decisionsRes,
            recsRes,
          ] = await Promise.allSettled([
            getSummary(t.id),
            getKeyConcepts(t.id),
            getActionItems(t.id),
            getKeyTakeaways(t.id),
            getLearningOutcomes(t.id),
            getTopics(t.id),
            getDecisions(t.id),
            getRecommendations(t.id),
          ]);
          if (cancelled) return;

          const hasInsights =
            (summaryRes.status === "fulfilled") ||
            (conceptsRes.status === "fulfilled" &&
              conceptsRes.value.key_concepts.length > 0) ||
            (actionsRes.status === "fulfilled" &&
              actionsRes.value.action_items.length > 0) ||
            (takeawaysRes.status === "fulfilled" &&
              takeawaysRes.value.key_takeaways.length > 0) ||
            (outcomesRes.status === "fulfilled" &&
              outcomesRes.value.learning_outcomes.length > 0) ||
            (topicsRes.status === "fulfilled" &&
              topicsRes.value.topics.length > 0) ||
            (decisionsRes.status === "fulfilled" &&
              decisionsRes.value.decisions.length > 0) ||
            (recsRes.status === "fulfilled" &&
              recsRes.value.recommendations.length > 0);

          if (hasInsights) {
            results.push({
              transcript: t,
              meeting,
              summary:
                summaryRes.status === "fulfilled"
                  ? summaryRes.value
                  : null,
              keyConcepts:
                conceptsRes.status === "fulfilled"
                  ? conceptsRes.value.key_concepts
                  : [],
              actionItems:
                actionsRes.status === "fulfilled"
                  ? actionsRes.value.action_items
                  : [],
              keyTakeaways:
                takeawaysRes.status === "fulfilled"
                  ? takeawaysRes.value.key_takeaways
                  : [],
              learningOutcomes:
                outcomesRes.status === "fulfilled"
                  ? outcomesRes.value.learning_outcomes
                  : [],
              topics:
                topicsRes.status === "fulfilled"
                  ? topicsRes.value.topics
                  : [],
              decisions:
                decisionsRes.status === "fulfilled"
                  ? decisionsRes.value.decisions
                  : [],
              recommendations:
                recsRes.status === "fulfilled"
                  ? recsRes.value.recommendations
                  : [],
            });
          }
        }

        if (!cancelled) {
          setInsightsData(results);
          setLoading(false);
        }
      } catch (err) {
        if (!cancelled) {
          setError(
            err instanceof Error ? err.message : "Failed to load insights"
          );
          setLoading(false);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const filteredData = useMemo(() => {
    let list = insightsData;
    if (search.trim()) {
      const q = search.toLowerCase();
      list = list.filter(
        (d) =>
          (d.meeting.topic ?? "").toLowerCase().includes(q) ||
          d.transcript.transcript_filename?.toLowerCase().includes(q) ||
          d.transcript.id.toLowerCase().includes(q) ||
          (d.summary?.summary_text ?? "").toLowerCase().includes(q) ||
          d.keyConcepts.some((kc) => kc.concept.toLowerCase().includes(q)) ||
          d.actionItems.some((ai) => ai.item_text.toLowerCase().includes(q)) ||
          d.keyTakeaways.some((kt) => kt.takeaway.toLowerCase().includes(q)) ||
          d.learningOutcomes.some((lo) => lo.outcome.toLowerCase().includes(q)) ||
          d.topics.some((t) => t.topic.toLowerCase().includes(q)) ||
          d.decisions.some((dc) => dc.decision.toLowerCase().includes(q)) ||
          d.recommendations.some((r) => r.recommendation.toLowerCase().includes(q))
      );
    }
    if (meetingFilter !== "all") {
      list = list.filter((d) => d.meeting.id === meetingFilter);
    }
    if (sectionFilter !== "all") {
      if (sectionFilter === "summary")
        list = list.filter((d) => d.summary !== null);
      if (sectionFilter === "key_concepts")
        list = list.filter((d) => d.keyConcepts.length > 0);
      if (sectionFilter === "action_items")
        list = list.filter((d) => d.actionItems.length > 0);
      if (sectionFilter === "key_takeaways")
        list = list.filter((d) => d.keyTakeaways.length > 0);
      if (sectionFilter === "learning_outcomes")
        list = list.filter((d) => d.learningOutcomes.length > 0);
      if (sectionFilter === "topics")
        list = list.filter((d) => d.topics.length > 0);
      if (sectionFilter === "decisions")
        list = list.filter((d) => d.decisions.length > 0);
      if (sectionFilter === "recommendations")
        list = list.filter((d) => d.recommendations.length > 0);
    }
    return list;
  }, [insightsData, search, meetingFilter, sectionFilter]);

  const pagedData = useMemo(() => {
    return filteredData.slice(offset, offset + PAGE_SIZE);
  }, [filteredData, offset]);

  const totalPages = Math.ceil(filteredData.length / PAGE_SIZE);
  const currentPage = Math.floor(offset / PAGE_SIZE) + 1;

  const totalSummaries = insightsData.filter(
    (d) => d.summary !== null
  ).length;
  const totalKeyConcepts = insightsData.reduce(
    (sum, d) => sum + d.keyConcepts.length,
    0
  );
  const totalActionItems = insightsData.reduce(
    (sum, d) => sum + d.actionItems.length,
    0
  );
  const totalKeyTakeaways = insightsData.reduce(
    (sum, d) => sum + d.keyTakeaways.length,
    0
  );
  const totalLearningOutcomes = insightsData.reduce(
    (sum, d) => sum + d.learningOutcomes.length,
    0
  );
  const totalTopics = insightsData.reduce(
    (sum, d) => sum + d.topics.length,
    0
  );
  const totalDecisions = insightsData.reduce(
    (sum, d) => sum + d.decisions.length,
    0
  );
  const totalRecommendations = insightsData.reduce(
    (sum, d) => sum + d.recommendations.length,
    0
  );

  const meetingsWithInsights = useMemo(() => {
    const ids = new Set<string>();
    insightsData.forEach((d) => ids.add(d.meeting.id));
    return meetings.filter((m) => ids.has(m.id));
  }, [insightsData, meetings]);

  const sectionCounts = useMemo(() => {
    return {
      all: insightsData.length,
      summary: insightsData.filter((d) => d.summary !== null).length,
      key_concepts: insightsData.filter((d) => d.keyConcepts.length > 0)
        .length,
      action_items: insightsData.filter((d) => d.actionItems.length > 0)
        .length,
      key_takeaways: insightsData.filter((d) => d.keyTakeaways.length > 0)
        .length,
      learning_outcomes: insightsData.filter((d) => d.learningOutcomes.length > 0)
        .length,
      topics: insightsData.filter((d) => d.topics.length > 0).length,
      decisions: insightsData.filter((d) => d.decisions.length > 0).length,
      recommendations: insightsData.filter((d) => d.recommendations.length > 0)
        .length,
    };
  }, [insightsData]);

  return (
    <AppShell>
      <div className="insights-page">
        <div className="page-header">
          <h1>Meeting Insights</h1>
          <p className="page-header-subtitle">
            AI-generated summaries, key concepts, action items, key takeaways,
            learning outcomes, topics, decisions, and recommendations from
            meeting transcripts
          </p>
        </div>

        {loading && <LoadingState message="Loading insights..." />}
        {error && <ErrorState message={error} />}

        {!loading && !error && (
          <>
            <div className="insights-summary">
              <div className="insights-summary-card">
                <div className="insights-summary-icon insights-summary-icon-primary">
                  <Lightbulb size={20} />
                </div>
                <div className="insights-summary-body">
                  <span className="insights-summary-value">
                    {insightsData.length}
                  </span>
                  <span className="insights-summary-label">
                    Meetings With Insights
                  </span>
                </div>
              </div>
              <div className="insights-summary-card">
                <div className="insights-summary-icon insights-summary-icon-success">
                  <FileText size={20} />
                </div>
                <div className="insights-summary-body">
                  <span className="insights-summary-value">
                    {totalSummaries}
                  </span>
                  <span className="insights-summary-label">
                    Total Summaries
                  </span>
                </div>
              </div>
              <div className="insights-summary-card">
                <div className="insights-summary-icon insights-summary-icon-warning">
                  <Hash size={20} />
                </div>
                <div className="insights-summary-body">
                  <span className="insights-summary-value">
                    {totalKeyConcepts}
                  </span>
                  <span className="insights-summary-label">
                    Total Key Concepts
                  </span>
                </div>
              </div>
              <div className="insights-summary-card">
                <div className="insights-summary-icon insights-summary-icon-error">
                  <ListChecks size={20} />
                </div>
                <div className="insights-summary-body">
                  <span className="insights-summary-value">
                    {totalActionItems}
                  </span>
                  <span className="insights-summary-label">
                    Total Action Items
                  </span>
                </div>
              </div>
              <div className="insights-summary-card">
                <div className="insights-summary-icon insights-summary-icon-primary">
                  <BookOpen size={20} />
                </div>
                <div className="insights-summary-body">
                  <span className="insights-summary-value">
                    {totalKeyTakeaways}
                  </span>
                  <span className="insights-summary-label">
                    Key Takeaways
                  </span>
                </div>
              </div>
              <div className="insights-summary-card">
                <div className="insights-summary-icon insights-summary-icon-success">
                  <GraduationCap size={20} />
                </div>
                <div className="insights-summary-body">
                  <span className="insights-summary-value">
                    {totalLearningOutcomes}
                  </span>
                  <span className="insights-summary-label">
                    Learning Outcomes
                  </span>
                </div>
              </div>
              <div className="insights-summary-card">
                <div className="insights-summary-icon insights-summary-icon-warning">
                  <Tag size={20} />
                </div>
                <div className="insights-summary-body">
                  <span className="insights-summary-value">
                    {totalTopics}
                  </span>
                  <span className="insights-summary-label">
                    Topics
                  </span>
                </div>
              </div>
              <div className="insights-summary-card">
                <div className="insights-summary-icon insights-summary-icon-error">
                  <Gavel size={20} />
                </div>
                <div className="insights-summary-body">
                  <span className="insights-summary-value">
                    {totalDecisions}
                  </span>
                  <span className="insights-summary-label">
                    Decisions
                  </span>
                </div>
              </div>
              <div className="insights-summary-card">
                <div className="insights-summary-icon insights-summary-icon-success">
                  <ThumbsUp size={20} />
                </div>
                <div className="insights-summary-body">
                  <span className="insights-summary-value">
                    {totalRecommendations}
                  </span>
                  <span className="insights-summary-label">
                    Recommendations
                  </span>
                </div>
              </div>
            </div>

            <section className="panel insights-panel">
              <div className="insights-toolbar">
                <div className="insights-search-wrap">
                  <Search
                    size={16}
                    className="insights-search-icon"
                  />
                  <input
                    type="text"
                    className="insights-search-input"
                    placeholder="Search by topic, concept, action item..."
                    value={search}
                    onChange={(e) => {
                      setSearch(e.target.value);
                      setOffset(0);
                    }}
                  />
                </div>
                <div className="insights-filters">
                  <Filter
                    size={14}
                    className="insights-filter-icon"
                  />
                  <select
                    className="filter-select"
                    value={sectionFilter}
                    onChange={(e) => {
                      setSectionFilter(e.target.value as Section);
                      setOffset(0);
                    }}
                  >
                    <option value="all">
                      All Sections ({sectionCounts.all})
                    </option>
                    <option value="summary">
                      Summaries ({sectionCounts.summary})
                    </option>
                    <option value="key_concepts">
                      Key Concepts ({sectionCounts.key_concepts})
                    </option>
                    <option value="action_items">
                      Action Items ({sectionCounts.action_items})
                    </option>
                    <option value="key_takeaways">
                      Key Takeaways ({sectionCounts.key_takeaways})
                    </option>
                    <option value="learning_outcomes">
                      Learning Outcomes ({sectionCounts.learning_outcomes})
                    </option>
                    <option value="topics">
                      Topics ({sectionCounts.topics})
                    </option>
                    <option value="decisions">
                      Decisions ({sectionCounts.decisions})
                    </option>
                    <option value="recommendations">
                      Recommendations ({sectionCounts.recommendations})
                    </option>
                  </select>
                  {meetingsWithInsights.length > 0 && (
                    <select
                      className="filter-select"
                      value={meetingFilter}
                      onChange={(e) => {
                        setMeetingFilter(e.target.value);
                        setOffset(0);
                      }}
                    >
                      <option value="all">All Meetings</option>
                      {meetingsWithInsights.map((m) => (
                        <option key={m.id} value={m.id}>
                          {m.topic ?? "Untitled Meeting"}
                        </option>
                      ))}
                    </select>
                  )}
                </div>
              </div>

              {pagedData.length > 0 ? (
                <div className="insights-list">
                  {pagedData.map((d) => (
                    <div key={d.transcript.id} className="insights-meeting-card">
                      <div className="insights-meeting-header">
                        <div className="insights-meeting-title-row">
                          <a
                            href={`#/meetings/${d.meeting.id}`}
                            className="insights-meeting-title"
                          >
                            {d.meeting.topic ?? "Untitled Meeting"}
                          </a>
                          <a
                            href={`#/meetings/${d.meeting.id}`}
                            className="insights-meeting-link"
                          >
                            <ExternalLink size={14} />
                            View Meeting
                          </a>
                        </div>
                        <div className="insights-meeting-meta">
                          <span className="insights-meta-item">
                            {formatRelativeTime(d.meeting.start_time)}
                          </span>
                          <span className="insights-meta-sep">&middot;</span>
                          <span className="insights-meta-item">
                            {d.keyConcepts.length} concepts
                          </span>
                          <span className="insights-meta-sep">&middot;</span>
                          <span className="insights-meta-item">
                            {d.actionItems.length} action items
                          </span>
                          <span className="insights-meta-sep">&middot;</span>
                          <span className="insights-meta-item">
                            {d.keyTakeaways.length} takeaways
                          </span>
                          <span className="insights-meta-sep">&middot;</span>
                          <span className="insights-meta-item">
                            {d.topics.length} topics
                          </span>
                          <span className="insights-meta-sep">&middot;</span>
                          <span className="insights-meta-item">
                            {d.decisions.length} decisions
                          </span>
                        </div>
                      </div>

                      {(sectionFilter === "all" ||
                        sectionFilter === "summary") &&
                        d.summary && (
                          <div className="insights-section">
                            <h3 className="insights-section-title">
                              <FileText size={16} />
                              Summary
                            </h3>
                            <p className="insights-summary-text">
                              {d.summary.summary_text}
                            </p>
                          </div>
                        )}

                      {(sectionFilter === "all" ||
                        sectionFilter === "key_concepts") &&
                        d.keyConcepts.length > 0 && (
                          <div className="insights-section">
                            <h3 className="insights-section-title">
                              <Hash size={16} />
                              Key Concepts
                            </h3>
                            <div className="insights-concepts-grid">
                              {d.keyConcepts.map((kc, i) => (
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

                      {(sectionFilter === "all" ||
                        sectionFilter === "action_items") &&
                        d.actionItems.length > 0 && (
                          <div className="insights-section">
                            <h3 className="insights-section-title">
                              <ListChecks size={16} />
                              Action Items
                            </h3>
                            <div className="insights-action-list">
                              {d.actionItems.map((ai, i) => (
                                <div
                                  key={i}
                                  className="insights-action-item"
                                >
                                  <div className="insights-action-text">
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

                      {(sectionFilter === "all" ||
                        sectionFilter === "key_takeaways") &&
                        d.keyTakeaways.length > 0 && (
                          <div className="insights-section">
                            <h3 className="insights-section-title">
                              <BookOpen size={16} />
                              Key Takeaways
                            </h3>
                            <div className="insights-action-list">
                              {d.keyTakeaways.map((kt, i) => (
                                <div
                                  key={i}
                                  className="insights-action-item"
                                >
                                  <div className="insights-action-text">
                                    {kt.takeaway}
                                  </div>
                                  {kt.context && (
                                    <div className="insights-action-meta">
                                      <span className="insights-concept-desc">
                                        {kt.context}
                                      </span>
                                    </div>
                                  )}
                                </div>
                              ))}
                            </div>
                          </div>
                        )}

                      {(sectionFilter === "all" ||
                        sectionFilter === "learning_outcomes") &&
                        d.learningOutcomes.length > 0 && (
                          <div className="insights-section">
                            <h3 className="insights-section-title">
                              <GraduationCap size={16} />
                              Learning Outcomes
                            </h3>
                            <div className="insights-action-list">
                              {d.learningOutcomes.map((lo, i) => (
                                <div
                                  key={i}
                                  className="insights-action-item"
                                >
                                  <div className="insights-action-text">
                                    {lo.outcome}
                                  </div>
                                  {lo.category && (
                                    <div className="insights-action-meta">
                                      <span className="badge badge-type">
                                        {lo.category}
                                      </span>
                                    </div>
                                  )}
                                </div>
                              ))}
                            </div>
                          </div>
                        )}

                      {(sectionFilter === "all" ||
                        sectionFilter === "topics") &&
                        d.topics.length > 0 && (
                          <div className="insights-section">
                            <h3 className="insights-section-title">
                              <Tag size={16} />
                              Topics
                            </h3>
                            <div className="insights-concepts-grid">
                              {d.topics.map((t, i) => (
                                <div key={i} className="insights-concept-card">
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

                      {(sectionFilter === "all" ||
                        sectionFilter === "decisions") &&
                        d.decisions.length > 0 && (
                          <div className="insights-section">
                            <h3 className="insights-section-title">
                              <Gavel size={16} />
                              Decisions
                            </h3>
                            <div className="insights-action-list">
                              {d.decisions.map((dc, i) => (
                                <div
                                  key={i}
                                  className="insights-action-item"
                                >
                                  <div className="insights-action-text">
                                    {dc.decision}
                                  </div>
                                  <div className="insights-action-meta">
                                    {dc.decided_by && (
                                      <span className="insights-action-assignee">
                                        {dc.decided_by}
                                      </span>
                                    )}
                                    {dc.rationale && (
                                      <span className="insights-concept-desc">
                                        {dc.rationale}
                                      </span>
                                    )}
                                  </div>
                                </div>
                              ))}
                            </div>
                          </div>
                        )}

                      {(sectionFilter === "all" ||
                        sectionFilter === "recommendations") &&
                        d.recommendations.length > 0 && (
                          <div className="insights-section">
                            <h3 className="insights-section-title">
                              <ThumbsUp size={16} />
                              Recommendations
                            </h3>
                            <div className="insights-action-list">
                              {d.recommendations.map((r, i) => (
                                <div
                                  key={i}
                                  className="insights-action-item"
                                >
                                  <div className="insights-action-text">
                                    {r.recommendation}
                                  </div>
                                  <div className="insights-action-meta">
                                    <PriorityBadge priority={r.priority} />
                                    {r.target_audience && (
                                      <span className="insights-action-assignee">
                                        {r.target_audience}
                                      </span>
                                    )}
                                  </div>
                                </div>
                              ))}
                            </div>
                          </div>
                        )}
                    </div>
                  ))}
                </div>
              ) : (
                <EmptyState
                  title="No Insights Found"
                  message={
                    search || meetingFilter !== "all" || sectionFilter !== "all"
                      ? "No insights match your filters. Try adjusting your search."
                      : "No meeting insights generated yet. Process a meeting to generate insights."
                  }
                />
              )}

              {totalPages > 1 && (
                <div className="pagination insights-pagination">
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
