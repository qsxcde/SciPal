<script setup lang="ts">
import { computed, ref } from "vue";
import MarkdownContent from "./MarkdownContent.vue";
import type { SourceRef } from "../api";
import type { ChatMessageViewModel, CurrentDocument } from "../types";

const props = defineProps<{
  documents: CurrentDocument[];
  displayFileName: string;
  hasPaper: boolean;
  indexedChunks: number;
  messages: ChatMessageViewModel[];
}>();

const latestSources = computed(() => {
  const assistantMessages = props.messages.filter((message) => message.role === "assistant");
  return assistantMessages.at(-1)?.sources ?? [];
});

const hasSources = computed(() => latestSources.value.length > 0);
const selectedSource = ref<SourceRef | null>(null);
const selectedSourceIndex = ref(0);
const isSourceDialogVisible = ref(false);

const selectedSourceTitle = computed(() =>
  selectedSource.value
    ? sourceTitle(selectedSourceIndex.value, selectedSource.value)
    : "来源详情",
);

function sourceDocumentName(source: SourceRef | null): string {
  const document = props.documents.find((item) => item.id === source?.paper_id);
  return document?.filename ?? source?.paper_id ?? props.displayFileName;
}

function sourceTitle(index: number, source: SourceRef): string {
  return `[${index + 1}] ${sourceDocumentName(source)} · ${source.section || "未命名章节"}`;
}

function sourceExcerpt(excerpt?: string | null): string {
  if (!excerpt) {
    return "后端已返回该来源，但暂未提供可展示的片段摘要。";
  }
  return excerpt.length > 140 ? `${excerpt.slice(0, 140)}...` : excerpt;
}

function sourceFullText(source: SourceRef | null): string {
  return source?.text_excerpt || "后端已返回该来源，但暂未提供可展示的原文片段。";
}

function openSourceDialog(source: SourceRef, index: number): void {
  selectedSource.value = source;
  selectedSourceIndex.value = index;
  isSourceDialogVisible.value = true;
}
</script>

<template>
  <aside
    class="sources-panel"
    aria-label="论文来源与证据"
  >
    <div>
      <div class="panel-label">
        论文上下文
      </div>
      <h2>来源与证据</h2>
    </div>

    <div class="sources-scroll">
      <section class="paper-status-card">
        <strong>{{ displayFileName }}</strong>
        <div class="progress-track">
          <span :style="{ width: hasPaper ? '100%' : '82%' }" />
        </div>
        <p>已索引 {{ indexedChunks }} 个片段 · {{ hasPaper ? `${documents.length} 篇论文` : "等待上传论文" }}</p>
      </section>

      <section
        v-if="documents.length > 0"
        class="evidence-card"
      >
        <div class="evidence-heading">
          <strong>当前会话论文</strong>
          <span>{{ documents.length }} 篇</span>
        </div>
        <p
          v-for="document in documents"
          :key="document.id"
        >
          {{ document.filename }} · {{ document.chunk_count }} 个片段 · {{ document.status }}
        </p>
      </section>

      <section
        v-if="!hasSources"
        class="evidence-card evidence-card--empty"
      >
        <div class="evidence-heading">
          <strong>等待真实来源</strong>
        </div>
        <p>上传论文并完成一次提问后，这里会展示后端检索返回的章节、片段编号和证据摘要。</p>
      </section>

      <button
        v-for="(source, index) in latestSources"
        v-else
        :key="`${source.paper_id ?? 'paper'}-${source.section}-${source.chunk_index}`"
        class="evidence-card"
        :class="{ 'evidence-card--raised': index === 0 }"
        type="button"
        @click="openSourceDialog(source, index)"
      >
        <div class="evidence-heading">
          <strong>{{ sourceTitle(index, source) }}</strong>
          <span>#{{ source.chunk_index }}</span>
        </div>
        <div class="evidence-excerpt">
          <span>“</span>
          <MarkdownContent :text="sourceExcerpt(source.text_excerpt)" />
          <span>”</span>
        </div>
      </button>
    </div>

    <section class="follow-card">
      <strong>推荐追问</strong>
      <button type="button">
        展示来源 #1 的原文依据
      </button>
      <button type="button">
        基于这些来源生成对比表
      </button>
    </section>

    <el-dialog
      v-model="isSourceDialogVisible"
      class="source-detail-dialog"
      width="560px"
      :title="selectedSourceTitle"
    >
      <div
        v-if="selectedSource"
        class="source-detail"
      >
        <div class="source-detail-meta">
          <span>片段 #{{ selectedSource.chunk_index }}</span>
          <span>{{ sourceDocumentName(selectedSource) }}</span>
        </div>
        <MarkdownContent :text="sourceFullText(selectedSource)" />
      </div>
    </el-dialog>
  </aside>
</template>
