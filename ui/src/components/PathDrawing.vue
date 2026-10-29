<script setup lang="ts">
// The path being built in the path builder, drawn as what it means (lib/pathreach.ts): you, then one node for each hop, then the stations that hear the last one. A node is labelled with who may take the hop: "any digi" (WIDE1-1:
// a home, fill-in, digipeater as well as a wide one; a house and a mast), "wide digi" (a hop of a WIDEn-N of n 2 or more: a mast), the call of a digipeater named (a mast) or of another alias, and a crossed circle for an alias
// that is no path. The nodes of one element of the path are on one chip, with the element as the field writes it under them (WIDE2-2 under its two wide hops; nothing more under a call, which is the node's label) and its × that
// takes it out: so the text and the hops are seen side by side. A chip that is no path is red; a hop after the second is amber, as the count of PathHops is. Each node's hover title says in a sentence who takes it, the text's
// says what n and N are. The picture is one line high whatever it holds and scrolls sideways when a long path does not fit, so that nothing under it moves as hops come and go.
import { t } from "@/i18n";
import { isAlias } from "@/lib/chain";
import { USUAL_HOPS, type HopKind, type PathMeaning, type PathPart } from "@/lib/pathreach";
import PathGlyph from "@/components/PathGlyph.vue";

defineProps<{ meaning: PathMeaning }>();
const emit = defineEmits<{ remove: [index: number] }>();

const GLYPH = { any: "any", wide: "wide", named: "wide", none: "none" } as const;

function label(part: PathPart, kind: HopKind): string {
  if (kind === "named") return part.text;
  return t(kind === "any" ? "pathbuilder.kind.any" : kind === "wide" ? "pathbuilder.kind.wide" : "pathbuilder.kind.none");
}

function title(part: PathPart, kind: HopKind, n: number): string {
  if (kind === "none") return part.problem;
  if (kind === "any") return t("pathbuilder.node.any", { n });
  if (kind === "wide") return t("pathbuilder.node.wide", { n });
  return isAlias(part.text) ? t("pathbuilder.node.alias", { n, alias: part.text }) : t("pathbuilder.node.call", { n, call: part.text });
}

const textTitle = (part: PathPart): string =>
  part.wide === null ? part.problem : t("pathbuilder.wide_part", { alias: part.text, n: part.wide.n, left: part.wide.left });
</script>

<template>
  <ol class="pathbuild-drawing" :aria-label="t('pathbuilder.drawing_label')">
    <li class="pathbuild-end" :title="t('pathbuilder.you_title')">
      <PathGlyph kind="you" />
      <span class="pathbuild-kind">{{ t("chain.you") }}</span>
    </li>
    <li v-if="meaning.parts.length === 0">
      <span class="hop-arrow" aria-hidden="true">→</span>
      <span class="pathbuild-direct muted">{{ t("pathbuilder.direct") }}</span>
    </li>
    <li v-for="(part, index) in meaning.parts" :key="`${index}-${part.text}`" class="pathbuild-part">
      <span class="hop-arrow" aria-hidden="true">→</span>
      <span class="pathbuild-chip" :class="{ bad: part.problem !== '' }">
        <span class="pathbuild-nodes">
          <span
            v-for="(kind, k) in part.kinds"
            :key="k"
            class="pathbuild-node"
            :class="{ over: kind !== 'none' && part.first + k > USUAL_HOPS }"
            :title="title(part, kind, part.first + k)"
          >
            <PathGlyph :kind="GLYPH[kind]" />
            <span class="pathbuild-kind" :class="{ mono: kind === 'named' }">{{ label(part, kind) }}</span>
          </span>
        </span>
        <span class="pathbuild-text">
          <span v-if="part.kinds[0] !== 'named'" class="mono" :title="textTitle(part)">{{ part.text }}</span>
          <button
            type="button"
            class="pathbuild-x"
            :aria-label="t('pathbuilder.remove', { call: part.text })"
            :title="t('pathbuilder.remove', { call: part.text })"
            @click="emit('remove', index)"
          >
            ×
          </button>
        </span>
      </span>
    </li>
    <li class="pathbuild-end" :title="t(meaning.parts.length === 0 ? 'pathbuilder.heard_direct' : 'pathbuilder.heard_by')">
      <span class="hop-arrow" aria-hidden="true">→</span>
      <PathGlyph kind="air" />
    </li>
  </ol>
</template>
