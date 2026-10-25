import { computed, ref } from "vue";
import type { SessionSnapshot } from "../api";
import { DEFAULT_PAPER_NAME, DEMO_SESSION_ID } from "../constants/app";
import { useChatStream } from "./useChatStream";
import { useSessionState } from "./useSessionState";

type SessionLoadResult = { messages: SessionSnapshot["messages"] } | null;

/**
 * Composes session state and chat streaming into a single app-facing API.
 *
 * 单例：`/`（对话）与 `/papers/:id`（阅读）是两个路由，但必须共享同一份
 * 会话与消息状态，否则来回切换会重复请求甚至断流。
 */
let store: ReturnType<typeof createPaperChat> | null = null;

export function usePaperChat(): ReturnType<typeof createPaperChat> {
  store ??= createPaperChat();
  return store;
}

function createPaperChat() {
  const errorMessage = ref("");
  /** 递增令牌：ChatComposer 监听它来抢占焦点（选区提问后） */
  const composerFocusToken = ref(0);

  function setErrorMessage(message: string): void {
    errorMessage.value = message;
  }

  function focusComposer(): void {
    composerFocusToken.value += 1;
  }

  const sessionState = useSessionState({ setErrorMessage });
  const chatStream = useChatStream({
    isUploading: sessionState.isUploading,
    setErrorMessage,
  });

  /** 会话用例统一返回快照消息，成功时刷新聊天区。 */
  function applySessionResult(result: SessionLoadResult): void {
    if (result) {
      chatStream.replaceMessages(result.messages);
    }
  }

  async function initializeSessions(): Promise<void> {
    applySessionResult(await sessionState.initializeSessions());
  }

  async function openSession(sessionId: string): Promise<void> {
    applySessionResult(await sessionState.openSession(sessionId));
  }

  async function handleUpload(file: File): Promise<void> {
    applySessionResult(await sessionState.handleUpload(file));
  }

  async function createEmptySession(): Promise<void> {
    applySessionResult(await sessionState.createEmptySession());
  }

  async function renameSession(sessionId: string, title: string): Promise<void> {
    applySessionResult(await sessionState.renameSession(sessionId, title));
  }

  async function deleteSession(sessionId: string): Promise<void> {
    const result = await sessionState.deleteSession(sessionId);
    if (result === null) {
      return;
    }
    if (result.nextSessionId) {
      await openSession(result.nextSessionId);
      return;
    }
    if (sessionState.paperSession.value === null) {
      chatStream.clearConversation();
    }
  }

  async function sendMessage(text: string): Promise<void> {
    let sessionId = sessionState.paperSession.value?.sessionId;
    if (sessionId === DEMO_SESSION_ID) {
      setErrorMessage("示例论文仅供预览，请先上传论文或新建会话后再继续提问。");
      return;
    }
    if (!sessionId) {
      const result = await sessionState.createEmptySession();
      applySessionResult(result);
      sessionId = sessionState.paperSession.value?.sessionId;
      if (!sessionId) {
        setErrorMessage("创建会话失败，请稍后重试。");
        return;
      }
    }
    await chatStream.sendMessage(text, sessionId);
  }

  /** 重新生成最后一条回答（示例会话与空闲态直接忽略）。 */
  async function regenerateLast(): Promise<void> {
    const sessionId = sessionState.paperSession.value?.sessionId;
    if (!sessionId) {
      return;
    }
    if (sessionId === DEMO_SESSION_ID) {
      setErrorMessage("示例论文仅供预览，请先上传论文或新建会话后再重新生成。");
      return;
    }
    await chatStream.regenerate(sessionId);
  }

  function stopStreaming(): void {
    chatStream.stopStreaming();
  }

  function useDemoPaper(): void {
    errorMessage.value = "";
    sessionState.paperSession.value = {
      sessionId: DEMO_SESSION_ID,
      docId: "demo-paper",
      fileName: DEFAULT_PAPER_NAME,
      chunkCount: 128,
    };
    sessionState.sessions.value = sessionState.sessions.value.map((session) => ({
      ...session,
      active: false,
    }));
    sessionState.documents.value = [];
    sessionState.uploadStatus.value = null;
    chatStream.useDemoPaper();
  }

  const currentSessionTitle = computed(() => {
    if (sessionState.paperSession.value?.sessionId === DEMO_SESSION_ID) {
      return "示例论文对话";
    }
    const activeSession = sessionState.sessions.value.find((session) => session.active);
    return activeSession?.title?.trim() || sessionState.displayFileName.value;
  });

  const currentPaperHint = computed(() => {
    const firstDocument = sessionState.documents.value[0];
    if (firstDocument?.filename) {
      return firstDocument.filename;
    }
    if (sessionState.paperSession.value?.sessionId === DEMO_SESSION_ID) {
      return sessionState.paperSession.value.fileName;
    }
    return "";
  });

  return {
    currentPaperHint,
    currentSessionTitle,
    displayFileName: sessionState.displayFileName,
    documents: sessionState.documents,
    draft: chatStream.draft,
    errorMessage,
    hasPaper: sessionState.hasPaper,
    indexedChunks: sessionState.indexedChunks,
    isStreaming: chatStream.isStreaming,
    isUploading: sessionState.isUploading,
    messages: chatStream.messages,
    paperSession: sessionState.paperSession,
    sessions: sessionState.sessions,
    uploadStatus: sessionState.uploadStatus,
    composerFocusToken,
    createEmptySession,
    deleteSession,
    focusComposer,
    handleUpload,
    initializeSessions,
    openSession,
    regenerateLast,
    renameSession,
    sendMessage,
    stopStreaming,
    togglePinSession: sessionState.togglePinSession,
    useDemoPaper,
  };
}
