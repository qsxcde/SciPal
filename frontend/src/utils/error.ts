/** 统一的错误信息提取：后端 detail 优先，其次兜底文案。 */
export function toErrorMessage(error: unknown, fallback: string): string {
  return error instanceof Error && error.message ? error.message : fallback;
}
