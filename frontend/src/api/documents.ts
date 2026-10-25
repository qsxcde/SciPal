import { fetchBinary } from "./client";

/** 拉取原始 PDF 字节，交由前端 pdf.js 渲染。 */
export function fetchDocumentFile(sessionId: string, documentId: string): Promise<ArrayBuffer> {
  return fetchBinary(`/sessions/${sessionId}/documents/${documentId}/file`, "读取 PDF 失败");
}
