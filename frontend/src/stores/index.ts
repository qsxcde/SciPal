/**
 * 跨组件树共享状态的唯一出口。
 *
 * 五个模块级单例（chat / library / reader / sourcePreview / auth）都从这里导出，
 * 目的是让「谁持有全局状态」有一个明确位置：登出与切换账号统一走 resetClientState()。
 * 后续若换成 Pinia，只需要替换本文件的实现，调用方不用动。
 */
export { useAuth } from "../composables/useAuth";
export { useLibrary } from "../composables/useLibrary";
export { usePaperChat, resetPaperChat } from "../composables/usePaperChat";
export { usePaperReader } from "../composables/usePaperReader";
export { useSourcePreview } from "../composables/useSourcePreview";
export { resetClientState } from "./reset";
