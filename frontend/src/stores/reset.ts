import { useLibrary } from "../composables/useLibrary";
import { resetPaperChat } from "../composables/usePaperChat";
import { usePaperReader } from "../composables/usePaperReader";
import { useSourcePreview } from "../composables/useSourcePreview";

/**
 * Clear every module-scoped store that survives the login route.
 *
 * The chat, library, reader and citation stores are shared singletons, so a new
 * account would otherwise see the previous account's sessions and paper text.
 * Call this before clearing the token.
 */
export function resetClientState(): void {
  resetPaperChat();
  useLibrary().reset();
  usePaperReader().reset();
  useSourcePreview().reset();
}
