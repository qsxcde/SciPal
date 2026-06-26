<script setup lang="ts">
/**
 * Renders a constrained markdown node tree recursively so rich text stays
 * component-driven and avoids unsafe HTML injection.
 */
import type { MarkdownAllowedTag, MarkdownNode } from "../utils/markdown";

defineProps<{
  node: MarkdownNode;
}>();

function resolveTag(tag: MarkdownAllowedTag): MarkdownAllowedTag {
  return tag;
}
</script>

<template>
  <span v-if="node.tag === null">{{ node.text }}</span>
  <component
    :is="resolveTag(node.tag)"
    v-else
  >
    <MarkdownNodeRenderer
      v-for="child in node.children"
      :key="child.id"
      :node="child"
    />
  </component>
</template>
