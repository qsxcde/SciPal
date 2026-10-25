import type { SessionSummary, SourceRef } from "../api";

/** 当前激活论文会话的轻量视图模型（侧栏 + 头部展示用）。 */
export type PaperSession = {
  sessionId: string;
  docId?: string;
  fileName: string;
  chunkCount: number;
};

/** 聊天区渲染用的消息模型，与持久化实体解耦。 */
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

/** 一次引用点击：序号用于角标，source 携带定位坐标。 */
export type SourceSelection = {
  index: number;
  source: SourceRef;
};

/** 阅读器大纲条目：key 用于高亮，blockId 用于跳转。 */
export type ReaderOutlineItem = {
  key: string;
  title: string;
  level: number;
  blockId: string;
  pageNumber: number;
};

/** 选区提问的两种意图。 */
export type SelectionAskMode = "explain" | "followup";
