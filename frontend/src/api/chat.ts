import { jsonRequest, openStream } from "./client";
import { readSseData } from "./sse";
import type { MessageChunk } from "./types";

export type StreamChatOptions = {
  /** 复用上一条提问重新生成，不会新增 user 消息 */
  regenerate?: boolean;
  /** 同一条提问的重试必须复用同一个 id，服务端据此去重 */
  clientMessageId?: string;
};

/** 流式问答：产出后端定义的 5 类事件，遇到 done 主动结束。 */
export async function* streamChat(
  sessionId: string,
  content: string,
  signal?: AbortSignal,
  options: StreamChatOptions = {},
): AsyncGenerator<MessageChunk> {
  const body = await openStream(
    `/sessions/${sessionId}/messages`,
    {
      method: "POST",
      ...jsonRequest({
        content,
        regenerate: options.regenerate ?? false,
        client_message_id: options.clientMessageId ?? null,
      }),
      signal,
    },
    "生成回答失败",
  );

  for await (const payload of readSseData(body)) {
    let event: MessageChunk;
    try {
      event = JSON.parse(payload) as MessageChunk;
    } catch {
      continue;
    }
    yield event;
    if (event.type === "done") {
      return;
    }
  }
}
