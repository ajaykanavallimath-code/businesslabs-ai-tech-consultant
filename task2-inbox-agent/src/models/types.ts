/**
 * Domain types and models for Task 2: Inbox Agent
 */

export type EmailCategory =
  | 'technical_support'
  | 'billing_and_payments'
  | 'account_and_login'
  | 'product_configuration'
  | 'feature_request'
  | 'complaints'
  | 'other_or_uncertain';

export const ALL_CATEGORIES: EmailCategory[] = [
  'technical_support',
  'billing_and_payments',
  'account_and_login',
  'product_configuration',
  'feature_request',
  'complaints',
  'other_or_uncertain',
];

export type ProcessingStatus =
  | 'received'
  | 'processing'
  | 'awaiting_review'
  | 'approved'
  | 'rejected'
  | 'escalated'
  | 'sent'
  | 'failed';

export interface CustomerEmail {
  id: string;
  senderEmail: string;
  senderName?: string;
  subject: string;
  body: string;
  receivedAt: string;
  status: ProcessingStatus;
  category?: EmailCategory;
  confidence?: number;
  draftId?: string;
  metadata?: Record<string, unknown>;
}

export interface KnowledgeBrainImage {
  url: string;
  caption?: string;
  context?: string;
}

export interface KnowledgeBrainSource {
  title: string;
  url: string;
  snippet: string;
  score: number;
  section?: string;
  images?: KnowledgeBrainImage[];
}

export interface KnowledgeBrainResponse {
  query: string;
  answer: string;
  confidence_score: number;
  escalated: boolean;
  escalation_id?: string | null;
  sources: KnowledgeBrainSource[];
  images: KnowledgeBrainImage[];
}

export interface DraftReply {
  id: string;
  emailId: string;
  category: EmailCategory;
  proposedBody: string;
  finalBody?: string;
  supportingSources: KnowledgeBrainSource[];
  supportingImages: KnowledgeBrainImage[];
  internalExplanation: string;
  uncertaintyWarnings: string[];
  humanReviewRequired: boolean;
  autoSendEligible: boolean;
  createdAt: string;
  updatedAt: string;
}

export type ReviewAction =
  | 'approve'
  | 'edit'
  | 'reject'
  | 'regenerate'
  | 'escalate';

export interface ReviewDecision {
  id: string;
  draftId: string;
  emailId: string;
  category: EmailCategory;
  action: ReviewAction;
  previousDraft: string;
  finalDraft?: string;
  reviewerFeedback?: string;
  reviewerName: string;
  timestamp: string;
}

export interface ReviewHistoryEntry {
  decisionId: string;
  action: ReviewAction;
  timestamp: string;
}

export interface CategoryAutonomyState {
  category: EmailCategory;
  consecutiveUneditedApprovals: number;
  isAutonomous: boolean;
  totalProcessed: number;
  totalApprovedUnedited: number;
  totalEdited: number;
  totalRejected: number;
  totalEscalated: number;
  recentHistory: ReviewHistoryEntry[];
  autonomyGrantedAt?: string | null;
  autonomyWithdrawnAt?: string | null;
  autonomyWithdrawalReason?: string | null;
}

export interface CategoryMetrics {
  category: EmailCategory;
  consecutiveUneditedApprovals: number;
  isAutonomous: boolean;
  totalProcessed: number;
  approvalRate: number;
  editRate: number;
  rejectionRate: number;
  escalationRate: number;
  recentEditOrRejectionRate: number;
  withdrawalReason?: string | null;
}

export interface OverallMetrics {
  totalEmails: number;
  totalDrafts: number;
  totalSent: number;
  totalAwaitingReview: number;
  totalEscalated: number;
  categories: Record<EmailCategory, CategoryMetrics>;
}

export interface SendResult {
  emailId: string;
  draftId: string;
  recipient: string;
  subject: string;
  body: string;
  sentAt: string;
  simulated: boolean;
  provider: string;
}
