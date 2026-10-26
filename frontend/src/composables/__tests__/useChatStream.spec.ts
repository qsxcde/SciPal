import { beforeEach, describe, expect, it, vi } from "vitest";

// 重试间隔置零，测试仍然走真实的「失败 → 重试 → 成功」分支。
vi.mock("../../constants/chat", () => ({
  SSE_RETRY_MAX_ATTEMPTS: 2,
  SSE_RETRY_BASE_DELAY_MS: 0,
}));

vi.mock("../../api", () => ({ streamChat: vi.fn() }));

import { streamChat } from "../../api";
import type { MessageChunk } from "../../api";
import { useChatStream } from "../useChatStream";

function streamOf(chunks: MessageChunk[]) {
  return (async function* () {
    for (const chunk of chunks) {
      yield chunk;
    }
  })();
}

function createChat() {
  const errors: string[] = [];
  const chat = useChatStream({
    isUploading: { value: false },
    // beginStreaming 会先清空错误（传空串），这里只记录真正的错误。
    setErrorMessage: (message: string) => {
      if (message) {
        errors.push(message);
      }
    },
  });
  return { chat, errors };
}

beforeEach(() => {
  vi.mocked(streamChat).mockReset();
});

describe("useChatStream", () => {
  it("累积 token 并保留 sources", async () => {
    vi.mocked(streamChat).mockReturnValue(
      streamOf([
        { type: "status", value: "generating" },
        { type: "token", value: "Hello" },
        { type: "token", value: " world" },
        { type: "sources", value: [{ section: "Intro", chunk_index: 0 }] },
        { type: "done" },
      ]),
    );
    const { chat, errors } = createChat();

    await chat.sendMessage("问题", "session-1");

    expect(chat.messages.value).toHaveLength(2);
    expect(chat.messages.value[0]).toMatchObject({ role: "user", text: "问题" });
    expect(chat.messages.value[1].text).toBe("Hello world");
    expect(chat.messages.value[1].sources?.[0].section).toBe("Intro");
    expect(chat.isStreaming.value).toBe(false);
    expect(errors).toEqual([]);
  });

  it("未知事件类型被忽略，不影响已生成内容", async () => {
    vi.mocked(streamChat).mockReturnValue(
      streamOf([
        { type: "token", value: "kept" },
        { type: "unknown_future_type", value: "x" } as unknown as MessageChunk,
        { type: "done" },
      ]),
    );
    const { chat, errors } = createChat();

    await chat.sendMessage("问题", "session-1");

    expect(chat.messages.value[1].text).toBe("kept");
    expect(errors).toEqual([]);
  });

  it("传输失败后自动重试，成功则不再报错", async () => {
    vi.mocked(streamChat).mockImplementationOnce(() => {
      throw new Error("network down");
    });
    vi.mocked(streamChat).mockReturnValueOnce(
      streamOf([{ type: "token", value: "recovered" }, { type: "done" }]),
    );
    const { chat, errors } = createChat();

    await chat.sendMessage("问题", "session-1");

    expect(vi.mocked(streamChat).mock.calls).toHaveLength(2);
    expect(chat.messages.value[1].text).toBe("recovered");
    expect(errors).toEqual([]);
  });

  it("重试耗尽后给出错误提示并结束流式状态", async () => {
    vi.mocked(streamChat).mockImplementation(() => {
      throw new Error("always down");
    });
    const { chat, errors } = createChat();

    await chat.sendMessage("问题", "session-1");

    expect(vi.mocked(streamChat).mock.calls).toHaveLength(3);
    expect(errors).toEqual(["always down"]);
    expect(chat.isStreaming.value).toBe(false);
    expect(chat.messages.value[1].text).toBe("");
  });

  it("主动中止不会产生错误提示", async () => {
    vi.mocked(streamChat).mockImplementation(() => {
      throw new DOMException("aborted", "AbortError");
    });
    const { chat, errors } = createChat();

    await chat.sendMessage("问题", "session-1");

    expect(errors).toEqual([]);
    expect(chat.isStreaming.value).toBe(false);
  });
});
