/**
 * 后端契约类型。
 *
 * 全部由 contracts/openapi.json 生成（npm run gen），不要手改；
 * 视图模型放 src/types/view.ts。
 */
import type { components } from "../contracts/openapi";

type Schemas = components["schemas"];

export type UserSummary = Schemas["UserResponse"];
export type AuthResult = Schemas["AuthResponse"];

export type SourceRef = Schemas["SourceRef"];
export type SourceBlockBox = Schemas["SourceBlockBox"];
export type SourceChunk = Schemas["SourceChunkResponse"];

export type DocumentStatus = Schemas["DocumentStage"];
export type PaperDocument = Schemas["DocumentSummary"];
export type DocumentUploadResult = Schemas["DocumentIntakeResponse"];
export type LibraryDocument = Schemas["LibraryDocumentSummary"];

export type PersistedMessage = Schemas["PersistedMessage"];
export type MessageStatus = Schemas["MessageStatus"];
export type SessionSummary = Schemas["SessionSummary"];
export type SessionSnapshot = Schemas["SessionSnapshot"];
export type SessionUpdatePayload = Schemas["SessionUpdateRequest"];
export type RetrievalIndexSummary = Schemas["RetrievalIndexSummary"];

export type PaperBlock = Schemas["PaperBlock"];
export type PaperContent = Schemas["DocumentContentResponse"];

/** SSE 事件载荷：六类事件的判别联合，同样来自 OpenAPI components。 */
export type MessageChunk = Schemas["ChatStreamEvent"];
