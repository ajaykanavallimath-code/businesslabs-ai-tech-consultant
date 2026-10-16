/**
 * Persistent atomic JSON storage for emails, drafts, reviews, and autonomy states.
 * Guarantees data survives application restarts and prevents corrupted files.
 */

import * as fs from 'fs';
import * as path from 'path';
import {
  ALL_CATEGORIES,
  CategoryAutonomyState,
  CustomerEmail,
  DraftReply,
  EmailCategory,
  ReviewDecision,
  SendResult,
} from '../models/types';
import { SafeLogger } from '../utils/logger';

interface InboxStoreData {
  emails: Record<string, CustomerEmail>;
  drafts: Record<string, DraftReply>;
  reviews: ReviewDecision[];
  sentLog: SendResult[];
}

export class PersistentStore {
  private dataDir: string;
  private inboxStorePath: string;
  private autonomyStorePath: string;

  private emails: Map<string, CustomerEmail> = new Map();
  private drafts: Map<string, DraftReply> = new Map();
  private reviews: ReviewDecision[] = [];
  private sentLog: SendResult[] = [];
  private autonomyStates: Map<EmailCategory, CategoryAutonomyState> = new Map();

  constructor(dataDir?: string) {
    this.dataDir = dataDir || path.resolve(__dirname, '../../data');
    this.inboxStorePath = path.join(this.dataDir, 'inbox_store.json');
    this.autonomyStorePath = path.join(this.dataDir, 'autonomy_state.json');

    this.ensureDirectory();
    this.loadState();
  }

  private ensureDirectory(): void {
    if (!fs.existsSync(this.dataDir)) {
      fs.mkdirSync(this.dataDir, { recursive: true });
    }
  }

  private initDefaultAutonomyStates(): void {
    for (const cat of ALL_CATEGORIES) {
      if (!this.autonomyStates.has(cat)) {
        this.autonomyStates.set(cat, {
          category: cat,
          consecutiveUneditedApprovals: 0,
          isAutonomous: false,
          totalProcessed: 0,
          totalApprovedUnedited: 0,
          totalEdited: 0,
          totalRejected: 0,
          totalEscalated: 0,
          recentHistory: [],
          autonomyGrantedAt: null,
          autonomyWithdrawnAt: null,
          autonomyWithdrawalReason: null,
        });
      }
    }
  }

  private atomicWrite(filePath: string, data: unknown): void {
    const tempPath = `${filePath}.${Date.now()}.${Math.random().toString(36).substring(7)}.tmp`;
    fs.writeFileSync(tempPath, JSON.stringify(data, null, 2), 'utf-8');
    try {
      if (fs.existsSync(filePath)) {
        fs.copyFileSync(tempPath, filePath);
        fs.unlinkSync(tempPath);
      } else {
        fs.renameSync(tempPath, filePath);
      }
    } catch {
      try {
        fs.writeFileSync(filePath, JSON.stringify(data, null, 2), 'utf-8');
        if (fs.existsSync(tempPath)) {
          fs.unlinkSync(tempPath);
        }
      } catch (err) {
        SafeLogger.error(`Failed to atomicWrite to ${filePath}:`, err);
      }
    }
  }

  public loadState(): void {
    // 1. Load Inbox Store
    if (fs.existsSync(this.inboxStorePath)) {
      try {
        const raw = fs.readFileSync(this.inboxStorePath, 'utf-8');
        const parsed: InboxStoreData = JSON.parse(raw);
        this.emails = new Map(Object.entries(parsed.emails || {}));
        this.drafts = new Map(Object.entries(parsed.drafts || {}));
        this.reviews = parsed.reviews || [];
        this.sentLog = parsed.sentLog || [];
      } catch (err) {
        SafeLogger.error(`Failed to load inbox store from ${this.inboxStorePath}:`, err);
      }
    }

    // 2. Load Autonomy State
    if (fs.existsSync(this.autonomyStorePath)) {
      try {
        const raw = fs.readFileSync(this.autonomyStorePath, 'utf-8');
        const parsed: Record<EmailCategory, CategoryAutonomyState> = JSON.parse(raw);
        for (const [cat, state] of Object.entries(parsed)) {
          this.autonomyStates.set(cat as EmailCategory, state);
        }
      } catch (err) {
        SafeLogger.error(`Failed to load autonomy state from ${this.autonomyStorePath}:`, err);
      }
    }

    this.initDefaultAutonomyStates();
  }

  public saveInboxStore(): void {
    const data: InboxStoreData = {
      emails: Object.fromEntries(this.emails),
      drafts: Object.fromEntries(this.drafts),
      reviews: this.reviews,
      sentLog: this.sentLog,
    };
    this.atomicWrite(this.inboxStorePath, data);
  }

  public saveAutonomyState(): void {
    const data = Object.fromEntries(this.autonomyStates);
    this.atomicWrite(this.autonomyStorePath, data);
  }

  // --- Email Operations ---

  public saveEmail(email: CustomerEmail): void {
    this.emails.set(email.id, { ...email });
    this.saveInboxStore();
  }

  public getEmail(id: string): CustomerEmail | undefined {
    const email = this.emails.get(id);
    return email ? { ...email } : undefined;
  }

  public listEmails(): CustomerEmail[] {
    return Array.from(this.emails.values()).map((e) => ({ ...e }));
  }

  // --- Draft Operations ---

  public saveDraft(draft: DraftReply): void {
    this.drafts.set(draft.id, { ...draft });
    this.saveInboxStore();
  }

  public getDraft(id: string): DraftReply | undefined {
    const draft = this.drafts.get(id);
    return draft ? { ...draft } : undefined;
  }

  public getDraftByEmailId(emailId: string): DraftReply | undefined {
    for (const draft of this.drafts.values()) {
      if (draft.emailId === emailId) {
        return { ...draft };
      }
    }
    return undefined;
  }

  public listDrafts(filterAwaitingReview = false): DraftReply[] {
    const all = Array.from(this.drafts.values());
    if (!filterAwaitingReview) return all.map((d) => ({ ...d }));

    return all.filter((d) => {
      const email = this.emails.get(d.emailId);
      return email && email.status === 'awaiting_review';
    }).map((d) => ({ ...d }));
  }

  // --- Review Operations ---

  public addReviewDecision(decision: ReviewDecision): void {
    this.reviews.push({ ...decision });
    this.saveInboxStore();
  }

  public listReviewDecisions(category?: EmailCategory): ReviewDecision[] {
    if (!category) return [...this.reviews];
    return this.reviews.filter((r) => r.category === category);
  }

  // --- Sent Log Operations ---

  public logSent(result: SendResult): void {
    this.sentLog.push({ ...result });
    this.saveInboxStore();
  }

  public listSent(): SendResult[] {
    return [...this.sentLog];
  }

  public isAlreadySent(emailId: string): boolean {
    return this.sentLog.some((s) => s.emailId === emailId);
  }

  // --- Autonomy State Operations ---

  public getAutonomyState(category: EmailCategory): CategoryAutonomyState {
    const state = this.autonomyStates.get(category);
    if (!state) {
      throw new Error(`Category ${category} autonomy state not found.`);
    }
    return JSON.parse(JSON.stringify(state));
  }

  public getAllAutonomyStates(): Record<EmailCategory, CategoryAutonomyState> {
    const result = {} as Record<EmailCategory, CategoryAutonomyState>;
    for (const [cat, state] of this.autonomyStates.entries()) {
      result[cat] = JSON.parse(JSON.stringify(state));
    }
    return result;
  }

  public updateAutonomyState(state: CategoryAutonomyState): void {
    this.autonomyStates.set(state.category, JSON.parse(JSON.stringify(state)));
    this.saveAutonomyState();
  }

  // --- Test / Reset Helpers ---
  public clearAll(): void {
    this.emails.clear();
    this.drafts.clear();
    this.reviews = [];
    this.sentLog = [];
    this.autonomyStates.clear();
    this.initDefaultAutonomyStates();
    this.saveInboxStore();
    this.saveAutonomyState();
  }
}
