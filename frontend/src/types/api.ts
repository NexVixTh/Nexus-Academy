/**
 * Type definitions matching the NEXUS ACADEMY FastAPI backend schema.
 */

export type BackendStatus = "checking" | "online" | "offline";

export interface HealthResponse {
  status: "ok";
}

export interface ModelTaskStatus {
  task: string;
  enabled: boolean;
  provider: string;
  model: string | null;
  capabilities: string[];
}

export interface ModelStatusResponse {
  tasks: ModelTaskStatus[];
}

export interface DocumentListItem {
  document_id: string;
  original_filename: string;
  content_type: string;
  ingested_at: string;
  record_count: number;
}

export interface DocumentListResponse {
  documents: DocumentListItem[];
}

export interface IngestionResponse {
  document_id: string;
  pages_or_slides_processed: number;
  records_created: number;
}

export interface DocumentAsset {
  asset_id: string;
  slide_number: number;
  mime_type: string;
  width: number;
  height: number;
  content_hash: string;
  byte_size: number;
}

export interface DocumentAssetsResponse {
  document_id: string;
  assets: DocumentAsset[];
}

export interface DocumentConceptItem {
  concept_id: string;
  document_id: string;
  name: string;
  description: string;
  source_record_id: string;
  source_type: "pdf_page" | "pptx_slide";
  page_or_slide_number: number;
  evidence_excerpt: string;
  is_visual: boolean;
  related_concept_names: string[];
}

export interface DocumentConceptsResponse {
  document_id: string;
  concept_count: number;
  concepts: DocumentConceptItem[];
}

export interface SearchResult {
  document_id: string;
  source_record_id: string;
  source_type: "pdf_page" | "pptx_slide";
  page_or_slide_number: number;
  excerpt: string;
  score: number;
}

export interface DocumentSearchResponse {
  document_id: string;
  results: SearchResult[];
}

export interface Citation {
  source_record_id: string;
  source_type: "pdf_page" | "pptx_slide";
  page_or_slide_number: number;
  excerpt: string;
}

export interface AskRequest {
  question: string;
}

export interface AskResponse {
  document_id: string;
  question: string;
  answer: string;
  citations: Citation[];
  abstained: boolean;
  abstention_reason: string | null;
}

export interface QuizOption {
  option_id: "A" | "B" | "C" | "D";
  text: string;
}

export interface QuizQuestion {
  question_id: string;
  question_text: string;
  concept_label: string;
  difficulty: "introductory" | "standard";
  options: QuizOption[];
  answer_key: "A" | "B" | "C" | "D";
  source_record_id: string;
  source_type: "pdf_page" | "pptx_slide";
  page_or_slide_number: number;
  supporting_excerpt: string;
}

export interface QuizResponse {
  quiz_id: string;
  document_id: string;
  learner_id?: string | null;
  requested_question_count: number;
  generated_question_count: number;
  limitation: string | null;
  questions: QuizQuestion[];
}

export interface QuizAnswerSelection {
  question_id: string;
  selected_option_id: "A" | "B" | "C" | "D";
}

export interface QuizSubmissionRequest {
  quiz_id: string;
  learner_id?: string | null;
  answers: QuizAnswerSelection[];
}

export interface QuizQuestionResult {
  question_id: string;
  concept_label: string | null;
  selected_option_id: string | null;
  is_correct: boolean | null;
  correct_option_id: string;
  feedback: string;
  source_record_id: string;
  source_type: "pdf_page" | "pptx_slide";
  page_or_slide_number: number;
  supporting_excerpt: string;
}

export interface QuizSubmissionResponse {
  quiz_id: string;
  document_id: string;
  total_questions: number;
  answered_count: number;
  correct_count: number;
  score_percentage_of_answered: number;
  results: QuizQuestionResult[];
}

export interface LearnerProfile {
  learner_id: string;
  created_at: string;
}

export type LearningStatus =
  | "not_attempted"
  | "struggling"
  | "learning"
  | "proficient";

export interface LearnerConceptProgress {
  document_id: string;
  concept_label: string;
  label_basis: "source_term_from_quiz_prompt";
  question_attempt_count: number;
  correct_count: number;
  mastery_estimate: number;
  recent_accuracy: number | null;
  evidence_sufficient: boolean;
  incorrect_count: number;
  learning_status: LearningStatus;
  explanation: string | null;
  recommended_action: string | null;
}

export interface LearnerProgressResponse {
  learner_id: string;
  created_at: string;
  quiz_attempt_count: number;
  question_attempt_count: number;
  correct_answer_rate: number;
  concepts_attempted: LearnerConceptProgress[];
  weak_concepts: LearnerConceptProgress[];
  insufficient_evidence_concepts: LearnerConceptProgress[];
}

export interface LearnerDocumentConceptItem {
  concept_id: string;
  concept_label: string;
  mastery_estimate: number | null;
  attempt_count: number;
  correct_count: number;
  incorrect_count: number;
  recent_accuracy: number | null;
  evidence_sufficient: boolean;
  learning_status: LearningStatus;
  explanation: string;
  recommended_action: string;
  source_record_id: string;
  source_type: "pdf_page" | "pptx_slide";
  page_or_slide_number: number;
  evidence_excerpt: string;
  is_visual: boolean;
  related_concept_names: string[];
}

export interface LearnerDocumentSummary {
  total_document_concepts: number;
  attempted_concept_count: number;
  proficient_concept_count: number;
  struggling_concept_count: number;
  learning_concept_count: number;
  not_attempted_concept_count: number;
  overall_mastery_estimate: number | null;
}

export interface LearnerDocumentProgressResponse {
  learner_id: string;
  document_id: string;
  quiz_attempt_count: number;
  question_attempt_count: number;
  correct_question_count: number;
  correct_answer_rate: number;
  summary: LearnerDocumentSummary;
  concepts: LearnerDocumentConceptItem[];
}

export interface LearnerAchievement {
  id: string;
  title: string;
  description: string;
  unlocked: boolean;
  unlocked_at: string | null;
}

export interface LearnerDailyMission {
  id: string;
  title: string;
  description: string;
  target: number;
  current: number;
  completed: boolean;
  xp_reward: number;
}

export interface LearnerGamificationResponse {
  learner_id: string;
  xp: number;
  level: number;
  level_title: string;
  xp_for_current_level: number;
  xp_for_next_level: number;
  level_progress_percentage: number;
  current_streak_days: number;
  quiz_count: number;
  questions_answered: number;
  questions_correct: number;
  proficient_concepts_count: number;
  achievements: LearnerAchievement[];
  daily_missions: LearnerDailyMission[];
}

