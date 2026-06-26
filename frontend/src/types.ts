import type { PaperDocument, SessionSummary, SourceRef } from "./api";

export type PaperSession = {
  sessionId: string;
  docId?: string;
  fileName: string;
  chunkCount: number;
};

export type ChatMessageViewModel = {
  id: string;
  role: "user" | "assistant";
  text: string;
  sources?: SourceRef[];
};

export type SidebarSessionItem = {
  id: string;
  isPinned: boolean;
  title: string;
  description: string;
  active: boolean;
};

export type ComposerToolState = {
  isSearchSelected: boolean;
  isMoreMenuVisible: boolean;
};

export type SessionSummaryViewModel = SessionSummary & {
  active: boolean;
};

export type CurrentDocument = PaperDocument;

export type SessionActionTarget = {
  id: string;
  title: string;
};

export type UploadPhase = "idle" | "parsing" | "indexing" | "ready" | "error";

export type UploadStatus = {
  fileName: string;
  fileSizeLabel: string;
  errorMessage?: string;
  phase: UploadPhase;
};

export type SuggestedPrompt = {
  id: string;
  text: string;
};
