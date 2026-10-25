<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from "vue";
import { Close } from "@element-plus/icons-vue";
import MarkdownContent from "./MarkdownContent.vue";
import { useSourcePreview } from "../composables/useSourcePreview";
import { formatPageRange } from "../utils/format";

const { selection, chunk, isLoading, errorMessage, close } = useSourcePreview();

const panelRef = ref<HTMLElement | null>(null);
const copied = ref(false);

const sectionTrail = computed(() => {
  if (chunk.value?.section_path.length) {
    return chunk.value.section_path;
  }
  return selection.value ? selection.value.source.section.split(" > ").filter(Boolean) : [];
});

const pageLabel = computed(() => {
  if (chunk.value) {
    return formatPageRange(chunk.value.page_start, chunk.value.page_end);
  }
  if (selection.value) {
    return formatPageRange(selection.value.source.page_start, selection.value.source.page_end);
  }
  return "";
});

function handleKeydown(event: KeyboardEvent): void {
  if (event.key === "Escape") {
    close();
  }
}

function handleBackdrop(): void {
  close();
}

async function copyText(): Promise<void> {
  const text = chunk.value?.text ?? selection.value?.source.text_excerpt ?? "";
  if (!text) {
    return;
  }
  try {
    await navigator.clipboard.writeText(text);
    copied.value = true;
    window.setTimeout(() => {
      copied.value = false;
    }, 1600);
  } catch {
    copied.value = false;
  }
}

watch(selection, async (value) => {
  if (value) {
    document.addEventListener("keydown", handleKeydown);
    await nextTick();
    panelRef.value?.focus();
  } else {
    document.removeEventListener("keydown", handleKeydown);
  }
});

onBeforeUnmount(() => {
  document.removeEventListener("keydown", handleKeydown);
});
</script>

<template>
  <Teleport to="body">
    <Transition name="source-drawer">
      <div v-if="selection" class="source-drawer" @click.self="handleBackdrop">
        <aside
          ref="panelRef"
          class="source-drawer__panel"
          role="dialog"
          aria-modal="true"
          aria-labelledby="source-drawer-title"
          tabindex="-1"
        >
          <header class="source-drawer__header">
            <div class="source-drawer__heading">
              <p class="source-drawer__eyebrow">
                引用 [{{ selection.index + 1 }}] · 块 {{ selection.source.chunk_index }}
                <span v-if="pageLabel">{{ pageLabel }}</span>
              </p>
              <h2 id="source-drawer-title" class="source-drawer__title">
                {{ sectionTrail[sectionTrail.length - 1] || selection.source.section }}
              </h2>
              <p v-if="sectionTrail.length > 1" class="source-drawer__trail">
                {{ sectionTrail.join(" / ") }}
              </p>
            </div>
            <el-button
              class="source-drawer__close"
              :icon="Close"
              circle
              text
              aria-label="关闭引用面板"
              @click="close"
            />
          </header>

          <div class="source-drawer__scroll">
            <section v-if="selection.source.text_excerpt" class="source-drawer__excerpt">
              <h3 class="source-drawer__label">命中片段</h3>
              <MarkdownContent :text="selection.source.text_excerpt" />
            </section>

            <section class="source-drawer__body">
              <h3 class="source-drawer__label">所在段落</h3>
              <p v-if="isLoading" class="source-drawer__state">正在读取原文…</p>
              <p v-else-if="errorMessage" class="source-drawer__state source-drawer__state--error">
                {{ errorMessage }}
              </p>
              <MarkdownContent v-else-if="chunk" :text="chunk.text" />
              <p v-else class="source-drawer__state">该引用来自历史记录，仅保留上面的命中片段。</p>
            </section>
          </div>

          <footer class="source-drawer__footer">
            <span class="source-drawer__hint">按 Esc 关闭</span>
            <el-button text class="source-drawer__copy" @click="copyText">
              {{ copied ? "已复制" : "复制原文" }}
            </el-button>
          </footer>
        </aside>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.source-drawer {
  position: fixed;
  inset: 0;
  z-index: 2400;
  display: flex;
  justify-content: flex-end;
  background: rgba(23, 32, 51, 0.18);
  backdrop-filter: blur(2px);
}

.source-drawer__panel {
  display: flex;
  width: min(440px, 100vw);
  height: 100%;
  flex-direction: column;
  background: var(--color-panel);
  border-left: 1px solid var(--color-border);
  box-shadow: -18px 0 48px rgba(48, 68, 101, 0.12);
  outline: none;
}

.source-drawer__header {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  justify-content: space-between;
  padding: 22px 22px 14px;
  border-bottom: 1px solid var(--color-border);
}

.source-drawer__heading {
  min-width: 0;
}

.source-drawer__eyebrow {
  margin: 0 0 6px;
  color: var(--color-text-muted);
  font-family: var(--font-mono);
  font-size: 11px;
  letter-spacing: 0.02em;
}

.source-drawer__title {
  margin: 0;
  overflow: hidden;
  color: var(--color-text);
  font-size: 17px;
  font-weight: 700;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.source-drawer__trail {
  margin: 6px 0 0;
  overflow: hidden;
  color: var(--color-text-muted);
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.source-drawer__close {
  flex: 0 0 auto;
}

.source-drawer__scroll {
  flex: 1;
  min-height: 0;
  padding: 18px 22px 24px;
  overflow-y: auto;
}

.source-drawer__label {
  margin: 0 0 8px;
  color: var(--color-text-muted);
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.source-drawer__excerpt {
  margin-bottom: 22px;
  padding: 12px 14px;
  color: var(--color-text-body);
  background: var(--color-accent-soft);
  border-left: 3px solid var(--color-accent);
  border-radius: 0 10px 10px 0;
}

.source-drawer__body {
  color: var(--color-text-body);
  font-size: 13px;
  line-height: 1.66;
}

.source-drawer__state {
  margin: 0;
  color: var(--color-text-muted);
  font-size: 13px;
}

.source-drawer__state--error {
  color: var(--color-danger);
}

.source-drawer__footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 22px;
  border-top: 1px solid var(--color-border);
}

.source-drawer__hint {
  color: var(--color-text-muted);
  font-size: 11px;
}

.source-drawer__copy {
  font-size: 12px;
}

.source-drawer-enter-active,
.source-drawer-leave-active {
  transition: opacity 0.18s ease;
}

.source-drawer-enter-active .source-drawer__panel,
.source-drawer-leave-active .source-drawer__panel {
  transition: transform 0.2s ease;
}

.source-drawer-enter-from,
.source-drawer-leave-to {
  opacity: 0;
}

.source-drawer-enter-from .source-drawer__panel,
.source-drawer-leave-to .source-drawer__panel {
  transform: translateX(24px);
}
</style>
