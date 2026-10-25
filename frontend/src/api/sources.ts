import { requestJson } from "./client";
import type { SourceChunk } from "./types";

/** 把回答里的引用还原为原文段落。 */
export function getSourceChunk(
  sessionId: string,
  documentId: string,
  chunkIndex: number,
): Promise<SourceChunk> {
  return requestJson<SourceChunk>(
    `/sessions/${sessionId}/documents/${documentId}/chunks/${chunkIndex}`,
    "读取原文失败",
  );
}
