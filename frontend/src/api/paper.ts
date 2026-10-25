import { requestJson } from "./client";
import type { PaperContent } from "./types";

/** 读取解析后的结构化正文，用于阅读器渲染与引用定位。 */
export function getPaperContent(sessionId: string, documentId: string): Promise<PaperContent> {
  return requestJson<PaperContent>(
    `/sessions/${sessionId}/documents/${documentId}/content`,
    "读取正文失败",
  );
}
