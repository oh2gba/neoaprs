<script setup lang="ts">
// The path being built in the path builder (PathBuilder.vue): drawn as what it means (PathDrawing: you, a node for each hop labelled with who takes it, the stations that hear the last one; each element with a × that takes it out);
// under it the path as the field will get it (OH2RDK-7,WIDE2-1, DIRECT for none), red with the reason in its title when it cannot go (the field's rule, or an alias that is no path), and the number of hops in all (the Ns of the
// WIDE aliases and one for each other element: WIDE2-2 is 2) as a tag, amber when it is more than the network usually allows and red when the path is no path, the reason in its hover title; and a field to type a hop into (a
// call with an SSID or an alias, one or several separated by commas, lower case taken as capitals) with Add, which is off while what is typed is no hop or the path is full. The picture is one line high and the count has a
// width of its own, so that what is below does not move as hops come and go.
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
