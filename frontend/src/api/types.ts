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
  page_start?: number | null;
  page_end?: number | null;
  block_ids?: string[] | null;
  confidence?: number | null;
};

/** 引用块在原页的位置，坐标为 0-1 归一化、左上角原点。 */
export type SourceBlockBox = {
  id: string;
  page_number: number;
  bbox: { x0: number; y0: number; x1: number; y1: number } | null;
};

/** 引用定位结果：后端按 (document_id, chunk_index) 还原的完整段落。 */
export type SourceChunk = {
  document_id: string;
  chunk_index: number;
  section: string;
  section_path: string[];
  page_start: number | null;
  page_end: number | null;
  type: string;
  text: string;
  block_ids: string[];
  blocks: SourceBlockBox[];
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

/** 文献库列表项：文档 + 所属会话标题。 */
export type LibraryDocument = {
  document_id: string;
  session_id: string;
  session_title: string;
  filename: string;
  status: string;
  chunk_count: number;
  file_size: number;
  parse_quality_status: string | null;
  updated_at: string;
};

/** 阅读器正文块，id 与 citation 的 block_ids 对齐。 */
export type PaperBlock = {
  id: string;
  type: string;
  text: string;
  section_path: string[];
  page_number: number;
};

export type PaperContent = {
  document_id: string;
  filename: string;
  status: string;
  parser_name: string | null;
  parse_quality_status: string | null;
  chunk_count: number;
  blocks: PaperBlock[];
};

export type MessageChunk =
  | { type: "token"; value: string }
  | { type: "sources"; value: SourceRef[] }
  | { type: "status"; value: string }
  | { type: "error"; value: string }
  | { type: "done" };
