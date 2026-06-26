import { computed, ref } from "vue";
import { archiveSession, createSession, getSession, listSessions, updateSession, uploadDocument } from "../api";
import type { CurrentDocument, PaperSession, SessionSummaryViewModel, UploadStatus } from "../types";

export type SessionSnapshotResult = Awaited<ReturnType<typeof getSession>>;

type UseSessionStateOptions = {
  setErrorMessage: (message: string) => void;
};

type ApplySnapshotPayload = {
  preserveUploadStatus?: boolean;
  snapshot: SessionSnapshotResult;
};

const UPLOAD_POLL_INTERVAL_MS = 1000;
const UPLOAD_MAX_POLLS = 600;

/**
 * Owns session list, active session, documents, and upload lifecycle state.
 *
 * Side effects: talks to session/document APIs and keeps active session state in sync.
 */
export const DEMO_SESSION_ID = "demo-session";

const STATUS_LABELS: Record<string, string> = {
  uploaded: "已上传",
  parsing: "解析中",
  parsed: "解析完成",
  chunked: "分块中",
  indexing: "索引构建中",
  ready: "就绪",
  failed: "处理失败",
};

export function useSessionState(options: UseSessionStateOptions) {
  const paperSession = ref<PaperSession | null>(null);
  const sessions = ref<SessionSummaryViewModel[]>([]);
  const documents = ref<CurrentDocument[]>([]);
  const isUploading = ref(false);
  const uploadStatus = ref<UploadStatus | null>(null);

  const hasPaper = computed(() => documents.value.length > 0);
  const displayFileName = computed(() => paperSession.value?.fileName ?? "新论文会话");
  const indexedChunks = computed(() => paperSession.value?.chunkCount ?? 0);

  function syncActiveSession(sessionId: string): void {
    sessions.value = sessions.value.map((session) => ({
      ...session,
      active: session.id === sessionId,
    }));
  }

  function applySnapshot(
    payload: ApplySnapshotPayload,
  ): { messages: SessionSnapshotResult["messages"] } {
    documents.value = payload.snapshot.documents;
    const docs = payload.snapshot.documents;
    const latestDocument = docs.length > 0
      ? [...docs].sort((a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime())[0]
      : null;
    paperSession.value = {
      sessionId: payload.snapshot.id,
      docId: latestDocument?.id,
      fileName: payload.snapshot.title || latestDocument?.filename || "新论文会话",
      chunkCount: payload.snapshot.indexed_chunks,
    };
    if (!payload.preserveUploadStatus) {
      uploadStatus.value = null;
    }
    syncActiveSession(payload.snapshot.id);
    return {
      messages: payload.snapshot.messages,
    };
  }

  function resetSessionState(): void {
    paperSession.value = null;
    documents.value = [];
    uploadStatus.value = null;
  }

  async function refreshSessions(activeSessionId?: string): Promise<void> {
    const result = await listSessions();
    sessions.value = result.map((session) => ({
      ...session,
      active: session.id === activeSessionId,
    }));
  }

  async function openSession(sessionId: string): Promise<{ messages: SessionSnapshotResult["messages"] } | null> {
    options.setErrorMessage("");
    try {
      const snapshot = await getSession(sessionId);
      const result = applySnapshot({ snapshot });
      await refreshSessions(sessionId);
      return result;
    } catch (error) {
      options.setErrorMessage(error instanceof Error ? error.message : "读取会话失败");
      return null;
    }
  }

  async function initializeSessions(): Promise<{ messages: SessionSnapshotResult["messages"] } | null> {
    try {
      await refreshSessions();
      if (sessions.value.length > 0) {
        return await openSession(sessions.value[0].id);
      }
      return null;
    } catch (error) {
      options.setErrorMessage(error instanceof Error ? error.message : "读取会话列表失败");
      return null;
    }
  }

  async function handleUpload(file: File): Promise<{ messages: SessionSnapshotResult["messages"] } | null> {
    options.setErrorMessage("");
    isUploading.value = true;
    uploadStatus.value = {
      fileName: file.name,
      fileSizeLabel: `${(file.size / (1024 * 1024)).toFixed(2)}MB`,
      phase: "parsing",
    };
    try {
      const activeSessionId = paperSession.value?.sessionId;
      const sessionId =
        !activeSessionId || activeSessionId === DEMO_SESSION_ID
          ? await createSession()
          : activeSessionId;
      const result = await uploadDocument(sessionId, file);
      const snapshot = await getSession(sessionId);
      const nextState = applySnapshot({
        preserveUploadStatus: true,
        snapshot,
      });
      await refreshSessions(sessionId);
      paperSession.value = {
        ...paperSession.value,
        sessionId,
        docId: result.document_id,
        fileName: snapshot.title || file.name,
        chunkCount: snapshot.indexed_chunks,
      };
      uploadStatus.value = {
        fileName: file.name,
        fileSizeLabel: `PDF ${Math.max(file.size / (1024 * 1024), 0.01).toFixed(2)}MB`,
        phase: result.session_status === "processing" ? "indexing" : "parsing",
      };
      const completedSnapshot = await waitForUploadCompletion(sessionId, result.document_id);
      if (!completedSnapshot) {
        return nextState;
      }
      const completedState = applySnapshot({
        preserveUploadStatus: true,
        snapshot: completedSnapshot,
      });
      const uploadedDocument = completedSnapshot.documents.find((document) => document.id === result.document_id);
      const uploadFailed = uploadedDocument?.status === "failed";
      uploadStatus.value = {
        fileName: file.name,
        fileSizeLabel: uploadFailed ? "" : `PDF ${Math.max(file.size / (1024 * 1024), 0.01).toFixed(2)}MB`,
        errorMessage: uploadFailed ? (uploadedDocument.error_message || "解析失败") : undefined,
        phase: uploadFailed ? "error" : "ready",
      };
      return completedState;
    } catch (error) {
      options.setErrorMessage(error instanceof Error ? error.message : "上传失败，请稍后重试");
      uploadStatus.value = {
        fileName: file.name,
        fileSizeLabel: "上传失败",
        errorMessage: "上传失败",
        phase: "error",
      };
      return null;
    } finally {
      isUploading.value = false;
    }
  }

  async function waitForUploadCompletion(
    sessionId: string,
    documentId: string,
  ): Promise<SessionSnapshotResult | null> {
    for (let attempt = 0; attempt < UPLOAD_MAX_POLLS; attempt += 1) {
      await new Promise((resolve) => window.setTimeout(resolve, UPLOAD_POLL_INTERVAL_MS));
      const snapshot = await getSession(sessionId);
      const document = snapshot.documents.find((item) => item.id === documentId);
      if (!document) {
        return snapshot;
      }
      if (document.status === "ready" || document.status === "failed") {
        return snapshot;
      }
      uploadStatus.value = {
        fileName: document.filename,
        fileSizeLabel: STATUS_LABELS[document.status] ?? document.status,
        phase: document.status === "indexing" || document.status === "chunked" ? "indexing" : "parsing",
      };
    }
    return null;
  }

  async function createEmptySession(): Promise<{ messages: SessionSnapshotResult["messages"] } | null> {
    options.setErrorMessage("");
    try {
      const sessionId = await createSession();
      uploadStatus.value = null;
      return await openSession(sessionId);
    } catch (error) {
      options.setErrorMessage(error instanceof Error ? error.message : "创建会话失败");
      return null;
    }
  }

  async function renameSession(sessionId: string, title: string): Promise<{ messages: SessionSnapshotResult["messages"] } | null> {
    options.setErrorMessage("");
    try {
      await updateSession(sessionId, { title });
      const activeSessionId = paperSession.value?.sessionId;
      await refreshSessions(activeSessionId);
      if (activeSessionId !== sessionId) {
        return null;
      }
      const snapshot = await getSession(sessionId);
      return applySnapshot({
        preserveUploadStatus: true,
        snapshot,
      });
    } catch (error) {
      options.setErrorMessage(error instanceof Error ? error.message : "重命名会话失败");
      return null;
    }
  }

  async function togglePinSession(sessionId: string): Promise<void> {
    const session = sessions.value.find((item) => item.id === sessionId);
    if (!session) {
      return;
    }
    options.setErrorMessage("");
    try {
      await updateSession(sessionId, { is_pinned: !session.is_pinned });
      await refreshSessions(paperSession.value?.sessionId);
    } catch (error) {
      options.setErrorMessage(error instanceof Error ? error.message : "置顶会话失败");
    }
  }

  async function deleteSession(sessionId: string): Promise<{ nextSessionId?: string } | null> {
    options.setErrorMessage("");
    try {
      await archiveSession(sessionId);
      const nextSessions = sessions.value.filter((item) => item.id !== sessionId);
      const activeSessionId =
        paperSession.value?.sessionId && paperSession.value.sessionId !== sessionId
          ? paperSession.value.sessionId
          : undefined;
      await refreshSessions(activeSessionId);
      if (paperSession.value?.sessionId === sessionId) {
        if (nextSessions.length > 0) {
          return { nextSessionId: nextSessions[0].id };
        }
        resetSessionState();
      }
      return {};
    } catch (error) {
      options.setErrorMessage(error instanceof Error ? error.message : "删除会话失败");
      return null;
    }
  }

  return {
    displayFileName,
    documents,
    hasPaper,
    indexedChunks,
    isUploading,
    paperSession,
    sessions,
    uploadStatus,
    createEmptySession,
    deleteSession,
    handleUpload,
    initializeSessions,
    openSession,
    refreshSessions,
    renameSession,
    resetSessionState,
    togglePinSession,
  };
}
