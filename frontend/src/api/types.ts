/**
 * 后端契约类型（手写镜像，字段与 REST/SSE 输出一一对应）。
 * 视图模型不要放这里，见 src/types/view.ts。
 */

export type UserSummary = {
  id: string;
  username: string;
};

export type AuthResult = {
  token: string;
  user: UserSummary;
};

export type SourceRef = {
  paper_id?: string | null;
  section: string;
  chunk_index: number;
  text_excerpt?: string | null;
};

export type DocumentStatus =
  "uploaded" | "parsing" | "parsed" | "chunked" | "indexing" | "ready" | "failed";

export type PaperDocument = {
  id: string;
  session_id: string;
  filename: string;
  file_path: string;
  mime_type: string;
  file_size: number;
  chunk_count: number;
  /** 后端返回 DocumentStage 字符串，宽松处理避免新状态导致前端白屏。 */
  status: DocumentStatus | (string & {});
  error_message?: string | null;
  created_at: string;
  updated_at: string;
};

export type PersistedMessage = {
  id: string;
  session_id: string;
  role: "user" | "assistant";
  content: string;
  sources: SourceRef[];
  status: string;
  created_at: string;
};

export type RetrievalIndexSummary = {
  id: string;
  session_id: string;
  index_path: string;
  chunks_path: string;
  status: string;
  updated_at: string;
};

export type SessionSummary = {
  id: string;
  title: string;
  user_id?: string | null;
  created_at: string;
  updated_at: string;
  last_opened_at: string;
  is_archived: boolean;
  is_pinned: boolean;
  document_count: number;
  message_count: number;
  indexed_chunks: number;
};

export type SessionSnapshot = {
  id: string;
  title: string;
  user_id?: string | null;
  created_at: string;
  updated_at: string;
  last_opened_at: string;
  is_archived: boolean;
  is_pinned: boolean;
  documents: PaperDocument[];
  messages: PersistedMessage[];
  indexed_chunks: number;
  retrieval_index?: RetrievalIndexSummary | null;
};

export type SessionUpdatePayload = {
  is_pinned?: boolean;
  title?: string;
};

export type DocumentUploadResult = {
  document_id: string;
  job_id: string;
  document_status: "uploaded";
  job_status: "queued" | "running";
  session_status: "processing";
};

export type MessageChunk =
  | { type: "token"; value: string }
  | { type: "sources"; value: SourceRef[] }
  | { type: "status"; value: string }
  | { type: "error"; value: string }
  | { type: "done" };
