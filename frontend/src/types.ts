export type DocumentStatus =
  | 'received'
  | 'processing'
  | 'needs_review'
  | 'ready'
  | 'failed';

export interface SectionSimplification {
  identifier: string;
  source_excerpt: string;
  source_text: string;
  plain_language: string;
}

export interface TokenUsageMetrics {
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  cost_usd: number;
}

export interface DocumentMetadataPublic {
  user_id: number;
  doc_id: string;
  title: string;
  created_at: string;
  status: DocumentStatus;
  summary?: string | null;
  obligations: string[];
  penalties: string[];
  deadlines: string[];
  risks: string[];
  simplified_sections: SectionSimplification[];
  token_usage: TokenUsageMetrics;
  extra?: Record<string, any>;
}

export interface DocumentListItem extends DocumentMetadataPublic {}

export interface SimplifiedResponse {
  user_id: number;
  doc_id: string;
  sections: SectionSimplification[];
}

export interface QaResponse {
  answer: string;
}

export interface TemplateGenerationResponse {
  user_id: number;
  country: string;
  prompt: string;
  template: string;
  token_usage: TokenUsageMetrics;
}
