export type DocumentStatus = 'received' | 'processing' | 'ready' | 'failed';

export interface SectionSimplification {
  identifier: string;
  source_excerpt: string;
  source_text: string;
  plain_language: string;
}

export interface DocumentMetadataPublic {
  document_id: string;
  title: string;
  created_at: string;
  status: DocumentStatus;
  summary?: string | null;
  obligations: string[];
  penalties: string[];
  deadlines: string[];
  risks: string[];
  simplified_sections: SectionSimplification[];
}

export interface DocumentListItem extends DocumentMetadataPublic {}

export interface SimplifiedResponse {
  document_id: string;
  sections: SectionSimplification[];
}

export interface QaResponse {
  answer: string;
}
