import { BYTES_PER_MB } from "../constants/app";

/**
 * 文件大小展示：统一保留两位小数并补 MB 单位。
 * 后端要求至少 0.01MB，避免 0.00MB 让用户误以为文件为空。
 */
export function formatFileSize(bytes: number, prefix = ""): string {
  const megabytes = Math.max(bytes / BYTES_PER_MB, 0.01);
  return `${prefix}${megabytes.toFixed(2)}MB`;
}
