import { jsonRequest, openStream } from "./client";
import { readSseData } from "./sse";
import type { MessageChunk } from "./types";

/** 流式问答：产出后端定义的 5 类事件，遇到 done 主动结束。 */
export async function* streamChat(
  sessionId: string,
  content: string,
  signal?: AbortSignal,
): AsyncGenerator<MessageChunk> {
  const body = await openStream(
    `/sessions/${sessionId}/messages`,
    { method: "POST", ...jsonRequest({ content }), signal },
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
