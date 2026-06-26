const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000";

type ApiErrorResponse = {
  detail?: string;
};

type RequestOptions = {
  body?: BodyInit | null;
  headers?: HeadersInit;
  method?: "DELETE" | "GET" | "PATCH" | "POST";
};

async function readError(res: Response, fallback: string): Promise<Error> {
  const err = (await res.json().catch(() => ({}))) as ApiErrorResponse;
  return new Error(err.detail ?? fallback);
}

async function requestJson<T>(
  path: string,
  fallback: string,
  options: RequestOptions = {},
): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, options);
  if (!res.ok) {
    throw await readError(res, fallback);
  }
  return (await res.json()) as T;
}

async function requestVoid(
  path: string,
  fallback: string,
  options: RequestOptions = {},
): Promise<void> {
  const res = await fetch(`${API_BASE}${path}`, options);
  if (!res.ok) {
    throw await readError(res, fallback);
  }
}

export async function createSession(): Promise<string> {
  const data = await requestJson<{ session_id: string }>("/sessions", "创建会话失败", {
    method: "POST",
  });
  return data.session_id;
}

export async function uploadDocument(
  sessionId: string,
  file: File
): Promise<{
  document_id: string;
  job_id: string;
  document_status: "uploaded";
  job_status: "queued" | "running";
  session_status: "processing";
}> {
  const form = new FormData();
  form.append("file", file);
  return requestJson<{
    document_id: string;
    job_id: string;
    document_status: "uploaded";
    job_status: "queued" | "running";
    session_status: "processing";
  }>(
    `/sessions/${sessionId}/documents`,
    "上传论文失败",
    {
      method: "POST",
      body: form,
    },
  );
}

export type SourceRef = {
  paper_id?: string | null;
  section: string;
  chunk_index: number;
  text_excerpt?: string | null;
};

export type PaperDocument = {
  id: string;
  session_id: string;
  filename: string;
  file_path: string;
  mime_type: string;
  file_size: number;
  chunk_count: number;
  status: string;
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

export async function listSessions(): Promise<SessionSummary[]> {
  return requestJson<SessionSummary[]>("/sessions", "读取会话列表失败");
}

export async function getSession(sessionId: string): Promise<SessionSnapshot> {
  return requestJson<SessionSnapshot>(`/sessions/${sessionId}`, "读取会话详情失败");
}

export async function archiveSession(sessionId: string): Promise<void> {
  return requestVoid(`/sessions/${sessionId}`, "归档会话失败", { method: "DELETE" });
}

export async function updateSession(
  sessionId: string,
  payload: SessionUpdatePayload,
): Promise<SessionSummary> {
  return requestJson<SessionSummary>(`/sessions/${sessionId}`, "更新会话失败", {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export type MessageChunk =
  | { type: "token"; value: string }
  | { type: "sources"; value: SourceRef[] }
  | { type: "status"; value: string }
  | { type: "error"; value: string }
  | { type: "done" };

export async function* streamChat(
  sessionId: string,
  content: string,
  signal?: AbortSignal,
): AsyncGenerator<MessageChunk> {
  const res = await fetch(`${API_BASE}/sessions/${sessionId}/messages`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ content }),
    signal,
  });
  if (!res.ok) {
    throw await readError(res, "生成回答失败");
  }
  if (!res.body) {
    throw new Error("后端没有返回可读取的流式响应");
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let dataBuffer = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";
    for (const line of lines) {
      if (line.startsWith("data: ")) {
        dataBuffer += line.slice(6);
      } else if (line === "" && dataBuffer) {
        let event: MessageChunk;
        try {
          event = JSON.parse(dataBuffer) as MessageChunk;
        } catch {
          dataBuffer = "";
          continue;
        }
        dataBuffer = "";
        yield event;
        if (event.type === "done") {
          return;
        }
      } else if (line === "") {
        continue;
      }
    }
  }
}
