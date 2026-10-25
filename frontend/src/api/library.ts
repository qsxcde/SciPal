import { requestJson } from "./client";
import type { LibraryDocument } from "./types";

/** 跨会话的文献库列表（已归档会话不计入）。 */
export function listLibraryDocuments(): Promise<LibraryDocument[]> {
  return requestJson<LibraryDocument[]>("/documents", "读取文献库失败");
}
