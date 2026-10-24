import { ref } from "vue";
import { streamChat } from "../api";
import type { SessionSnapshot } from "../api";
import { SSE_RETRY_BASE_DELAY_MS, SSE_RETRY_MAX_ATTEMPTS } from "../constants/chat";
import type { ChatMessageViewModel } from "../types";
import { toErrorMessage } from "../utils/error";

function createMessageId(prefix: string): string {
  return `${prefix}-${crypto.randomUUID()}`;
}

function mapPersistedMessages(messages: SessionSnapshot["messages"]): ChatMessageViewModel[] {
  return messages.map((message) => ({
    id: message.id,
    role: message.role,
    text: message.content,
    sources: message.sources,
  }));
}

function delay(milliseconds: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError";
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

  /** 入队并返回数组内的响应式引用，后续增量更新直接改它。 */
  function appendMessage(message: ChatMessageViewModel): ChatMessageViewModel {
    messages.value.push(message);
    return messages.value[messages.value.length - 1];
  }

  function replaceMessages(nextMessages: SessionSnapshot["messages"]): void {
    messages.value = mapPersistedMessages(nextMessages);
  }

  function clearConversation(): void {
    abortController?.abort();
    abortController = null;
    messages.value = [];
    draft.value = "";
  }

  async function consumeOnce(
    sessionId: string,
    content: string,
    assistant: ChatMessageViewModel,
  ): Promise<void> {
    let accumulated = "";
    assistant.text = "";

    for await (const chunk of streamChat(sessionId, content, abortController?.signal)) {
      if (chunk.type === "token") {
        accumulated += chunk.value;
        assistant.text = accumulated;
      } else if (chunk.type === "sources") {
        assistant.sources = chunk.value;
      } else if (chunk.type === "error") {
        assistant.text = accumulated || `生成失败：${chunk.value}`;
        return;
      }
    }
  }

  async function sendMessage(text: string, sessionId?: string): Promise<void> {
    const content = text.trim();
    if (!content || isStreaming.value || options.isUploading.value || !sessionId) {
      return;
    }

    appendMessage({ id: createMessageId("user"), role: "user", text: content });
    const assistant = appendMessage({
      id: createMessageId("assistant"),
      role: "assistant",
      text: "",
    });
    draft.value = "";
    options.setErrorMessage("");
    isStreaming.value = true;
    abortController = new AbortController();

    try {
      let lastError: unknown;
      for (let attempt = 0; attempt <= SSE_RETRY_MAX_ATTEMPTS; attempt += 1) {
        if (attempt > 0) {
          await delay(SSE_RETRY_BASE_DELAY_MS * 2 ** (attempt - 1));
        }
        try {
          await consumeOnce(sessionId, content, assistant);
          return;
        } catch (error) {
          if (isAbortError(error)) {
            throw error;
          }
          lastError = error;
        }
      }
      throw lastError;
    } catch (error) {
      if (isAbortError(error)) {
        return;
      }
      options.setErrorMessage(toErrorMessage(error, "生成回答失败，请稍后重试"));
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
        text: `**主要局限**可以归纳为三点：

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
    draft,
    isStreaming,
    messages,
    clearConversation,
    replaceMessages,
    sendMessage,
    useDemoPaper,
  };
}
