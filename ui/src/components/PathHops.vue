<script setup lang="ts">
// The path being built: the drawing (PathDrawing), the path text as the field will get it (orange
// with the reason when it cannot go), the number of hops as a tag (warn plate above the usual
// limit), and a field to type hops with Add. The count has a fixed width so that nothing below
// moves.
import { computed, ref } from "vue";
import PathDrawing from "@/components/PathDrawing.vue";
import TagMark from "@/components/TagMark.vue";
import { t } from "@/i18n";
import { pathOf, typedHops } from "@/lib/pathbuilder";
import type { PathMeaning } from "@/lib/pathreach";
import { LIMITS } from "@/protocol/lists";

const props = defineProps<{ hops: readonly string[]; meaning: PathMeaning; problem: string }>();
const emit = defineEmits<{ remove: [index: number]; add: [calls: string[]] }>();

const typed = ref("");
const found = computed(() => typedHops(typed.value));
const room = computed(() => LIMITS.path.maxCalls - props.hops.length);
const addable = computed(() => found.value !== null && found.value.length <= room.value);
const tone = computed(() => (props.meaning.level === "bad" ? "bad" : props.meaning.level === "many" ? "warn" : "neutral"));

function add(): void {
  if (!addable.value || found.value === null) return;
  emit("add", found.value);
  typed.value = "";
}
</script>

<template>
  <div class="pathbuild-path">
    <PathDrawing :meaning="meaning" @remove="emit('remove', $event)" />
    <p class="pathbuild-result">
      <output class="mono" :class="{ invalid: problem !== '' }" :title="problem || undefined">{{ pathOf(hops) }}</output>
      <span class="pathbuild-total">
        <TagMark class="pathbuild-count" :tone="tone" :title="meaning.reason || undefined">{{ t("pathbuilder.count", { n: meaning.hops }) }}</TagMark>
      </span>
    </p>
    <div class="pathbuild-type">
      <input
        v-model="typed"
        class="input mono"
        :class="{ invalid: typed.trim() !== '' && !addable }"
        type="text"
        :placeholder="t('pathbuilder.type_placeholder')"
        :aria-label="t('pathbuilder.type_label')"
        autocomplete="off"
        spellcheck="false"
        @keydown.enter.prevent="add"
      />
      <button type="button" class="btn" :disabled="!addable" @click="add">{{ t("pathbuilder.add") }}</button>
    </div>
  </div>
</template>
