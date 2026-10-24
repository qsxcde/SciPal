import { computed, ref } from "vue";
import {
  archiveSession,
  createSession,
  getSession,
  listSessions,
  updateSession,
  uploadDocument,
} from "../api";
import type { PaperDocument, SessionSummary } from "../api";
import { DEMO_SESSION_ID } from "../constants/app";
import {
  INDEXING_DOCUMENT_STATUSES,
  UPLOAD_MAX_POLLS,
  UPLOAD_POLL_INTERVAL_MS,
  UPLOAD_STATUS_LABELS,
} from "../constants/upload";
import type { PaperSession, SessionSummaryViewModel, UploadStatus } from "../types";
import { toErrorMessage } from "../utils/error";
import { formatFileSize } from "../utils/format";

export type SessionSnapshotResult = Awaited<ReturnType<typeof getSession>>;

type UseSessionStateOptions = {
  setErrorMessage: (message: string) => void;
};

type ApplySnapshotPayload = {
  preserveUploadStatus?: boolean;
  snapshot: SessionSnapshotResult;
};

/** 会话列表统一打上 active 标记，避免多处重复 map。 */
function withActiveFlag(
  sessions: SessionSummary[],
  activeSessionId?: string,
): SessionSummaryViewModel[] {
  return sessions.map((session) => ({
    ...session,
    active: session.id === activeSessionId,
  }));
}

function pickLatestDocument(documents: PaperDocument[]): PaperDocument | null {
  if (documents.length === 0) {
    return null;
  }
  return [...documents].sort(
    (a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime(),
  )[0];
}

/**
 * Owns session list, active session, documents, and upload lifecycle state.
 *
 * Side effects: talks to session/document APIs and keeps active session state in sync.
 */
export function useSessionState(options: UseSessionStateOptions) {
  const paperSession = ref<PaperSession | null>(null);
  const sessions = ref<SessionSummaryViewModel[]>([]);
  const documents = ref<PaperDocument[]>([]);
  const isUploading = ref(false);
  const uploadStatus = ref<UploadStatus | null>(null);

  const hasPaper = computed(() => documents.value.length > 0);
  const displayFileName = computed(() => paperSession.value?.fileName ?? "新论文会话");
  const indexedChunks = computed(() => paperSession.value?.chunkCount ?? 0);

  function syncActiveSession(sessionId: string): void {
    sessions.value = withActiveFlag(sessions.value, sessionId);
  }

  function applySnapshot(payload: ApplySnapshotPayload): {
    messages: SessionSnapshotResult["messages"];
  } {
    const { snapshot } = payload;
    documents.value = snapshot.documents;
    const latestDocument = pickLatestDocument(snapshot.documents);
    paperSession.value = {
      sessionId: snapshot.id,
      docId: latestDocument?.id,
      fileName: snapshot.title || latestDocument?.filename || "新论文会话",
      chunkCount: snapshot.indexed_chunks,
    };
    if (!payload.preserveUploadStatus) {
      uploadStatus.value = null;
    }
    syncActiveSession(snapshot.id);
    return { messages: snapshot.messages };
  }

  function resetSessionState(): void {
    paperSession.value = null;
    documents.value = [];
    uploadStatus.value = null;
  }

  async function refreshSessions(activeSessionId?: string): Promise<void> {
    sessions.value = withActiveFlag(await listSessions(), activeSessionId);
  }

  async function openSession(
    sessionId: string,
  ): Promise<{ messages: SessionSnapshotResult["messages"] } | null> {
    options.setErrorMessage("");
    try {
      const snapshot = await getSession(sessionId);
      const result = applySnapshot({ snapshot });
      await refreshSessions(sessionId);
      return result;
    } catch (error) {
      options.setErrorMessage(toErrorMessage(error, "读取会话失败"));
      return null;
    }
  }

  async function initializeSessions(): Promise<{
    messages: SessionSnapshotResult["messages"];
  } | null> {
    try {
      await refreshSessions();
      if (sessions.value.length > 0) {
        return await openSession(sessions.value[0].id);
      }
      return null;
    } catch (error) {
      options.setErrorMessage(toErrorMessage(error, "读取会话列表失败"));
      return null;
    }
  }

  async function handleUpload(
    file: File,
  ): Promise<{ messages: SessionSnapshotResult["messages"] } | null> {
    options.setErrorMessage("");
    isUploading.value = true;
    uploadStatus.value = {
      fileName: file.name,
      fileSizeLabel: formatFileSize(file.size),
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
      const nextState = applySnapshot({ preserveUploadStatus: true, snapshot });
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
        fileSizeLabel: formatFileSize(file.size, "PDF "),
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
      const uploadedDocument = completedSnapshot.documents.find(
        (document) => document.id === result.document_id,
      );
      const uploadFailed = uploadedDocument?.status === "failed";
      uploadStatus.value = {
        fileName: file.name,
        fileSizeLabel: uploadFailed ? "" : formatFileSize(file.size, "PDF "),
        errorMessage: uploadFailed ? uploadedDocument.error_message || "解析失败" : undefined,
        phase: uploadFailed ? "error" : "ready",
      };
      return completedState;
    } catch (error) {
      options.setErrorMessage(toErrorMessage(error, "上传失败，请稍后重试"));
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
        fileSizeLabel: UPLOAD_STATUS_LABELS[document.status] ?? document.status,
        phase: INDEXING_DOCUMENT_STATUSES.has(document.status) ? "indexing" : "parsing",
      };
    }
    return null;
  }

  async function createEmptySession(): Promise<{
    messages: SessionSnapshotResult["messages"];
  } | null> {
    options.setErrorMessage("");
    try {
      const sessionId = await createSession();
      uploadStatus.value = null;
      return await openSession(sessionId);
    } catch (error) {
      options.setErrorMessage(toErrorMessage(error, "创建会话失败"));
      return null;
    }
  }

  async function renameSession(
    sessionId: string,
    title: string,
  ): Promise<{ messages: SessionSnapshotResult["messages"] } | null> {
    options.setErrorMessage("");
    try {
      await updateSession(sessionId, { title });
      const activeSessionId = paperSession.value?.sessionId;
      await refreshSessions(activeSessionId);
      if (activeSessionId !== sessionId) {
        return null;
      }
      const snapshot = await getSession(sessionId);
      return applySnapshot({ preserveUploadStatus: true, snapshot });
    } catch (error) {
      options.setErrorMessage(toErrorMessage(error, "重命名会话失败"));
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
      options.setErrorMessage(toErrorMessage(error, "置顶会话失败"));
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
      options.setErrorMessage(toErrorMessage(error, "删除会话失败"));
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
    renameSession,
    togglePinSession,
  };
}
