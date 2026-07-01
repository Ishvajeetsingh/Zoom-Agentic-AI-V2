import { apiGet } from "./client";
import type { PaginatedListResponse } from "../types/api";

export interface SummaryResponse {
  transcript_id: string;
  summary_text: string;
  model_used: string | null;
}

export interface KeyConceptItem {
  concept: string;
  description: string;
  importance_order: number;
}

export interface KeyConceptsResponse {
  transcript_id: string;
  key_concepts: KeyConceptItem[];
}

export interface ActionItemItem {
  item_text: string;
  assignee: string | null;
  priority: string | null;
  due_date: string | null;
}

export interface ActionItemsResponse {
  transcript_id: string;
  action_items: ActionItemItem[];
}

export interface KeyTakeawayItem {
  takeaway: string;
  context: string | null;
}

export interface KeyTakeawaysResponse {
  transcript_id: string;
  key_takeaways: KeyTakeawayItem[];
}

export interface LearningOutcomeItem {
  outcome: string;
  category: string | null;
}

export interface LearningOutcomesResponse {
  transcript_id: string;
  learning_outcomes: LearningOutcomeItem[];
}

export interface TopicItem {
  topic: string;
  relevance: string | null;
}

export interface TopicsResponse {
  transcript_id: string;
  topics: TopicItem[];
}

export interface DecisionItem {
  decision: string;
  rationale: string | null;
  decided_by: string | null;
}

export interface DecisionsResponse {
  transcript_id: string;
  decisions: DecisionItem[];
}

export interface RecommendationItem {
  recommendation: string;
  priority: string | null;
  target_audience: string | null;
}

export interface RecommendationsResponse {
  transcript_id: string;
  recommendations: RecommendationItem[];
}

export interface FullInsightsResponse {
  transcript_id: string;
  summary_text: string;
  model_used: string | null;
  key_concepts: KeyConceptItem[];
  action_items: ActionItemItem[];
  key_takeaways: KeyTakeawayItem[];
  learning_outcomes: LearningOutcomeItem[];
  topics: TopicItem[];
  decisions: DecisionItem[];
  recommendations: RecommendationItem[];
}

export function getSummary(transcriptId: string) {
  return apiGet<SummaryResponse>(`/transcripts/${transcriptId}/summary`);
}

export function getKeyConcepts(transcriptId: string) {
  return apiGet<KeyConceptsResponse>(`/transcripts/${transcriptId}/key-concepts`);
}

export function getActionItems(transcriptId: string) {
  return apiGet<ActionItemsResponse>(`/transcripts/${transcriptId}/action-items`);
}

export interface LearningOutputItem {
  id: string;
  transcript_id: string;
  meeting_id: string;
  chunk_id: string | null;
  output_type: string;
  content: Record<string, unknown>;
  difficulty: string | null;
  category: string | null;
  bloom_taxonomy: string | null;
  educational_score: number | null;
  created_at: string;
}

export interface LearningOutputListResponse {
  items: LearningOutputItem[];
  total: number;
  offset: number;
  limit: number;
}

export interface OutputCountItem {
  output_type: string;
  count: number;
}

export interface OutputCountsResponse {
  transcript_id: string;
  counts: OutputCountItem[];
}

export interface LearningOutputParams {
  output_type?: string;
  category?: string;
  difficulty?: string;
  bloom?: string;
  offset?: number;
  limit?: number;
  order?: "asc" | "desc";
  top?: number;
}

export function getLearningOutputs(transcriptId: string, params?: LearningOutputParams) {
  return apiGet<LearningOutputListResponse>(
    `/transcripts/${transcriptId}/outputs`,
    params as Record<string, string | number>
  );
}

export function getOutputCounts(transcriptId: string) {
  return apiGet<OutputCountsResponse>(`/transcripts/${transcriptId}/outputs/count`);
}

export function getKeyTakeaways(transcriptId: string) {
  return apiGet<KeyTakeawaysResponse>(`/transcripts/${transcriptId}/key-takeaways`);
}

export function getLearningOutcomes(transcriptId: string) {
  return apiGet<LearningOutcomesResponse>(`/transcripts/${transcriptId}/learning-outcomes`);
}

export function getTopics(transcriptId: string) {
  return apiGet<TopicsResponse>(`/transcripts/${transcriptId}/topics`);
}

export function getDecisions(transcriptId: string) {
  return apiGet<DecisionsResponse>(`/transcripts/${transcriptId}/decisions`);
}

export function getRecommendations(transcriptId: string) {
  return apiGet<RecommendationsResponse>(`/transcripts/${transcriptId}/recommendations`);
}

export function getFullInsights(transcriptId: string) {
  return apiGet<FullInsightsResponse>(`/transcripts/${transcriptId}/full-insights`);
}
