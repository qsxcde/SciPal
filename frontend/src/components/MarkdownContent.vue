<script setup lang="ts">
import { computed } from "vue";
import MarkdownNodeRenderer from "./MarkdownNodeRenderer.vue";
import { parseMarkdown } from "../utils/markdown";

const props = defineProps<{
  text: string;
}>();

/**
 * Converts markdown text into a constrained render tree that can be displayed
 * safely inside chat bubbles and evidence cards.
 */
const blocks = computed(() => parseMarkdown(props.text));
</script>

<template>
  <div class="markdown-content">
    <MarkdownNodeRenderer
      v-for="block in blocks"
      :key="block.id"
      :node="block"
    />
  </div>
</template>
