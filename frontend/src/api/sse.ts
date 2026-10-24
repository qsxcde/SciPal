/**
 * SSE 分帧：把字节流还原为「一行一个 data:」的事件负载。
 * 只负责协议解析，业务类型判断留给调用方。
 */
export async function* readSseData(
  body: ReadableStream<Uint8Array>,
): AsyncGenerator<string, void, unknown> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let dataBuffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) {
      break;
    }
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";

    for (const line of lines) {
      if (line.startsWith("data: ")) {
        dataBuffer += line.slice(6);
        continue;
      }
      if (line !== "") {
        continue;
      }
      if (!dataBuffer) {
        continue;
      }
      const payload = dataBuffer;
      dataBuffer = "";
      yield payload;
    }
  }
}
