import MarkdownIt from "markdown-it";
import type Token from "markdown-it/lib/token.mjs";

export type MarkdownNode = {
  id: string;
  tag: MarkdownAllowedTag | null;
  text?: string;
  children?: MarkdownNode[];
};

export type MarkdownAllowedTag =
  | "br"
  | "blockquote"
  | "code"
  | "em"
  | "h3"
  | "h4"
  | "h5"
  | "li"
  | "p"
  | "pre"
  | "strong"
  | "ul";

const markdown = new MarkdownIt({
  breaks: true,
  html: false,
  linkify: false,
});

const BLOCK_TAG_MAP: Record<string, MarkdownAllowedTag> = {
  blockquote: "blockquote",
  h1: "h3",
  h2: "h4",
  h3: "h5",
  h4: "h5",
  h5: "h5",
  h6: "h5",
  li: "li",
  p: "p",
  pre: "pre",
  ul: "ul",
  ol: "ul",
};

const INLINE_TAG_MAP: Record<string, MarkdownAllowedTag> = {
  code: "code",
  em: "em",
  strong: "strong",
};

function createNodeId(prefix: string, index: number): string {
  return `${prefix}-${index}`;
}

function createTextNode(text: string, index: number): MarkdownNode | null {
  if (!text) {
    return null;
  }
  return {
    id: createNodeId("text", index),
    tag: null,
    text,
  };
}

function collectInlineTokens(tokens: Token[], startIndex: number): MarkdownNode[] {
  const nodes: MarkdownNode[] = [];

  for (const [offset, token] of tokens.entries()) {
    const nodeIndex = startIndex + offset;
    if (token.type === "text") {
      const textNode = createTextNode(token.content, nodeIndex);
      if (textNode) {
        nodes.push(textNode);
      }
      continue;
    }

    if (token.type === "softbreak" || token.type === "hardbreak") {
      nodes.push({
        id: createNodeId("break", nodeIndex),
        tag: "br",
      });
      continue;
    }

    if (token.type === "code_inline") {
      nodes.push({
        id: createNodeId("inline-code", nodeIndex),
        tag: "code",
        children: [
          {
            id: createNodeId("inline-code-text", nodeIndex),
            tag: null,
            text: token.content,
          },
        ],
      });
      continue;
    }

    if (token.type === "image") {
      const textNode = createTextNode(`[${token.content || "图片"}]`, nodeIndex);
      if (textNode) {
        nodes.push(textNode);
      }
      continue;
    }

    const normalizedTag = INLINE_TAG_MAP[token.tag];
    if (!normalizedTag || !token.children) {
      continue;
    }

    nodes.push({
      id: createNodeId(normalizedTag, nodeIndex),
      tag: normalizedTag,
      children: collectInlineTokens(token.children, nodeIndex * 10 + 1),
    });
  }

  return nodes;
}

function readList(tokens: Token[], startIndex: number): { nextIndex: number; node: MarkdownNode } {
  const children: MarkdownNode[] = [];
  let cursor = startIndex + 1;

  while (
    cursor < tokens.length &&
    tokens[cursor].type !== "bullet_list_close" &&
    tokens[cursor].type !== "ordered_list_close"
  ) {
    if (tokens[cursor].type === "list_item_open") {
      const inlineToken = tokens[cursor + 2];
      children.push({
        id: createNodeId("list-item", cursor),
        tag: "li",
        children: collectInlineTokens(inlineToken?.children ?? [], cursor * 10 + 1),
      });
      cursor += 4;
      continue;
    }
    cursor += 1;
  }

  return {
    nextIndex: cursor + 1,
    node: {
      id: createNodeId("list", startIndex),
      tag: "ul",
      children,
    },
  };
}

function readBlockquote(tokens: Token[], startIndex: number): { nextIndex: number; node: MarkdownNode } {
  const inlineToken = tokens[startIndex + 2];
  return {
    nextIndex: startIndex + 4,
    node: {
      id: createNodeId("blockquote", startIndex),
      tag: "blockquote",
      children: collectInlineTokens(inlineToken?.children ?? [], startIndex * 10 + 1),
    },
  };
}

function readHeading(tokens: Token[], startIndex: number): { nextIndex: number; node: MarkdownNode } {
  const headingOpenToken = tokens[startIndex];
  const inlineToken = tokens[startIndex + 1];
  return {
    nextIndex: startIndex + 3,
    node: {
      id: createNodeId("heading", startIndex),
      tag: BLOCK_TAG_MAP[headingOpenToken.tag] ?? "h5",
      children: collectInlineTokens(inlineToken?.children ?? [], startIndex * 10 + 1),
    },
  };
}

/**
 * Parses markdown into a constrained node tree so the UI can render rich text
 * without using v-html or exposing arbitrary HTML.
 */
export function parseMarkdown(text: string): MarkdownNode[] {
  const normalizedText = text.trim();
  if (!normalizedText) {
    return [];
  }

  const tokens = markdown.parse(normalizedText, {});
  const nodes: MarkdownNode[] = [];
  let index = 0;

  while (index < tokens.length) {
    const token = tokens[index];

    if (token.type === "inline") {
      nodes.push({
        id: createNodeId("paragraph", index),
        tag: "p",
        children: collectInlineTokens(token.children ?? [], index * 10 + 1),
      });
      index += 1;
      continue;
    }

    if (token.type === "fence" || token.type === "code_block") {
      nodes.push({
        id: createNodeId("code-block", index),
        tag: "pre",
        children: [
          {
            id: createNodeId("code-block-code", index),
            tag: "code",
            children: [
              {
                id: createNodeId("code-block-text", index),
                tag: null,
                text: token.content,
              },
            ],
          },
        ],
      });
      index += 1;
      continue;
    }

    if (token.type === "bullet_list_open" || token.type === "ordered_list_open") {
      const result = readList(tokens, index);
      nodes.push(result.node);
      index = result.nextIndex;
      continue;
    }

    if (token.type === "blockquote_open") {
      const result = readBlockquote(tokens, index);
      nodes.push(result.node);
      index = result.nextIndex;
      continue;
    }

    if (token.type === "heading_open") {
      const result = readHeading(tokens, index);
      nodes.push(result.node);
      index = result.nextIndex;
      continue;
    }

    index += 1;
  }

  return nodes;
}
