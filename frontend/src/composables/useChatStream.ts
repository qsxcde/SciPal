import { ref } from "vue";
import { streamChat } from "../api";
import type { ChatMessageViewModel } from "../types";
import type { SessionSnapshotResult } from "./useSessionState";

const DEFAULT_PAPER_NAME = "Transformer 综述.pdf";
const SSE_RETRY_MAX_ATTEMPTS = 2;
const SSE_RETRY_BASE_DELAY_MS = 1000;

function createMessageId(prefix: string): string {
  return `${prefix}-${crypto.randomUUID()}`;
}

function mapPersistedMessages(messages: SessionSnapshotResult["messages"]): ChatMessageViewModel[] {
  return messages.map((message) => ({
    id: message.id,
    role: message.role,
    text: message.content,
    sources: message.sources,
  }));
}

type UseChatStreamOptions = {
  isUploading: { value: boolean };
  setErrorMessage: (message: string) => void;
};

/**
 * Owns draft input, rendered chat messages, and streaming answer lifecycle.
 *
 * Side effects: consumes streaming chat events and appends transient assistant output.
 */
export function useChatStream(options: UseChatStreamOptions) {
  const draft = ref("");
  const isStreaming = ref(false);
  const messages = ref<ChatMessageViewModel[]>([]);
  let abortController: AbortController | null = null;

  function replaceMessages(nextMessages: SessionSnapshotResult["messages"]): void {
    messages.value = mapPersistedMessages(nextMessages);
  }

  function clearConversation(): void {
    abortController?.abort();
    abortController = null;
    messages.value = [];
    draft.value = "";
  }

  async function sendMessage(text: string, sessionId?: string): Promise<void> {
    const content = text.trim();
    if (!content || isStreaming.value || options.isUploading.value || !sessionId) {
      return;
    }

    const assistantId = createMessageId("assistant");
    messages.value.push(
      { id: createMessageId("user"), role: "user", text: content },
      { id: assistantId, role: "assistant", text: "" },
    );
    draft.value = "";
    options.setErrorMessage("");
    isStreaming.value = true;
    abortController = new AbortController();

    try {
      let accumulated = "";
      let assistantMessage: ChatMessageViewModel | undefined;
      let lastError: unknown;
      let success = false;

      for (let attempt = 0; attempt <= SSE_RETRY_MAX_ATTEMPTS && !success; attempt++) {
        if (attempt > 0) {
          const delay = SSE_RETRY_BASE_DELAY_MS * Math.pow(2, attempt - 1);
          await new Promise((resolve) => setTimeout(resolve, delay));
        }
        try {
          accumulated = "";
          for await (const chunk of streamChat(sessionId, content, abortController.signal)) {
            if (chunk.type === "token") {
              accumulated += chunk.value;
              if (assistantMessage) {
                assistantMessage.text = accumulated;
              } else {
                messages.value = messages.value.map((message) =>
                  message.id === assistantId ? { ...message, text: accumulated } : message,
                );
              }
            } else if (chunk.type === "sources") {
              if (assistantMessage) {
                assistantMessage.sources = chunk.value;
              } else {
                messages.value = messages.value.map((message) =>
                  message.id === assistantId ? { ...message, sources: chunk.value } : message,
                );
              }
            } else if (chunk.type === "error") {
              const errorText = accumulated || `生成失败：${chunk.value}`;
              if (assistantMessage) {
                assistantMessage.text = errorText;
              } else {
                messages.value = messages.value.map((message) =>
                  message.id === assistantId ? { ...message, text: errorText } : message,
                );
              }
              success = true;
              break;
            }
            if (!assistantMessage) {
              assistantMessage = messages.value.find((m) => m.id === assistantId);
            }
          }
          success = true;
        } catch (error) {
          if (error instanceof DOMException && error.name === "AbortError") {
            throw error;
          }
          lastError = error;
        }
      }

      if (!success && lastError) {
        throw lastError;
      }
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") {
        return;
      }
      options.setErrorMessage(error instanceof Error ? error.message : "生成回答失败，请稍后重试");
    } finally {
      isStreaming.value = false;
      abortController = null;
    }
  }

  function useDemoPaper(): void {
    messages.value = [
      {
        id: createMessageId("user"),
        role: "user",
        text: "这篇论文的主要局限是什么？",
      },
      {
        id: createMessageId("assistant"),
        role: "assistant",
        text:
          `**主要局限**可以归纳为三点：

- 评估覆盖范围仍然有限
- 检索结果对分块策略较敏感
- 长文档场景下的计算开销较高

最关键的限制在于，系统表现高度依赖 \`chunking\` 策略和向量表示质量，不同领域迁移时结果可能明显波动。`,
        sources: [
          {
            section: "第 4.2 节",
            chunk_index: 1,
            text_excerpt:
              "**评估覆盖范围**主要集中在标准问答数据集，作者指出真实科研阅读中的跨章节推理仍需要进一步验证。",
          },
          {
            section: "第 9 页",
            chunk_index: 2,
            text_excerpt:
              "实验显示，当 `chunk size` 或召回数量变化时，答案一致性会受到影响，这也是论文讨论的核心限制之一。",
          },
        ],
      },
    ];
  }

  return {
    defaultPaperName: DEFAULT_PAPER_NAME,
    draft,
    isStreaming,
    messages,
    clearConversation,
    replaceMessages,
    sendMessage,
    useDemoPaper,
  };
}
