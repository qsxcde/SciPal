import { requestJson, requestVoid } from "./client";
import type { LibraryDocument } from "./types";

/** 跨会话的文献库列表（已归档会话不计入）。 */
export function listLibraryDocuments(): Promise<LibraryDocument[]> {
  return requestJson<LibraryDocument[]>("/documents", "读取文献库失败");
}

/** 删除单篇文档；后端会同时清掉分块、磁盘产物并重建索引。 */
export function deleteDocument(sessionId: string, documentId: string): Promise<void> {
  return requestVoid(`/sessions/${sessionId}/documents/${documentId}`, "删除论文失败", {
    method: "DELETE",
  });
}
