import { BYTES_PER_MB } from "../constants/app";

/**
 * 文件大小展示：统一保留两位小数并补 MB 单位。
 * 后端要求至少 0.01MB，避免 0.00MB 让用户误以为文件为空。
 */
export function formatFileSize(bytes: number, prefix = ""): string {
  const megabytes = Math.max(bytes / BYTES_PER_MB, 0.01);
  return `${prefix}${megabytes.toFixed(2)}MB`;
}

/** 页码展示：单页 `p.4`，跨页 `p.4-5`，缺省返回空串。 */
export function formatPageRange(start?: number | null, end?: number | null): string {
  if (start == null && end == null) {
    return "";
  }
  if (start == null) {
    return `p.${end}`;
  }
  if (end == null || end === start) {
    return `p.${start}`;
  }
  return `p.${start}-${end}`;
}
