/** 上传轮询与阶段文案。 */

export const UPLOAD_POLL_INTERVAL_MS = 1000;
export const UPLOAD_MAX_POLLS = 600;

export const UPLOAD_STATUS_LABELS: Record<string, string> = {
  uploaded: "已上传",
  parsing: "解析中",
  parsed: "解析完成",
  chunked: "分块中",
  indexing: "索引构建中",
  ready: "就绪",
  failed: "处理失败",
};

/** 已进入索引阶段的文档状态，用于决定进度条文案。 */
export const INDEXING_DOCUMENT_STATUSES = new Set(["chunked", "indexing"]);
