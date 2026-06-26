import { computed, ref } from "vue";
import { useChatStream } from "./useChatStream";
import { useSessionState, DEMO_SESSION_ID } from "./useSessionState";

/**
 * Composes session state and chat streaming into a single app-facing API
 * while keeping each concern in a smaller dedicated composable.
 */
export function usePaperChat() {
  const errorMessage = ref("");

  function setErrorMessage(message: string): void {
    errorMessage.value = message;
  }

  const sessionState = useSessionState({ setErrorMessage });
  const chatStream = useChatStream({
    isUploading: sessionState.isUploading,
    setErrorMessage,
  });

  async function initializeSessions(): Promise<void> {
    const result = await sessionState.initializeSessions();
    if (result) {
      chatStream.replaceMessages(result.messages);
    }
  }

  async function openSession(sessionId: string): Promise<void> {
    const result = await sessionState.openSession(sessionId);
    if (result) {
      chatStream.replaceMessages(result.messages);
    }
  }

  async function handleUpload(file: File): Promise<void> {
    const result = await sessionState.handleUpload(file);
    if (result) {
      chatStream.replaceMessages(result.messages);
    }
  }

  async function createEmptySession(): Promise<void> {
    const result = await sessionState.createEmptySession();
    if (result) {
      chatStream.replaceMessages(result.messages);
    }
  }

  async function renameSession(sessionId: string, title: string): Promise<void> {
    const result = await sessionState.renameSession(sessionId, title);
    if (result) {
      chatStream.replaceMessages(result.messages);
    }
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
      if (!result) {
        return;
      }
      chatStream.replaceMessages(result.messages);
      sessionId = sessionState.paperSession.value?.sessionId;
      if (!sessionId) {
        setErrorMessage("创建会话失败，请稍后重试。");
        return;
      }
    }
    await chatStream.sendMessage(text, sessionId);
  }

  function useDemoPaper(): void {
    errorMessage.value = "";
    sessionState.paperSession.value = {
      sessionId: DEMO_SESSION_ID,
      docId: "demo-paper",
      fileName: chatStream.defaultPaperName,
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
    createEmptySession,
    deleteSession,
    handleUpload,
    initializeSessions,
    openSession,
    renameSession,
    sendMessage,
    togglePinSession: sessionState.togglePinSession,
    useDemoPaper,
  };
}
