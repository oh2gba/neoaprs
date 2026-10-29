<script setup lang="ts">
// The path being built in the path builder (PathBuilder.vue): its hops in order as chips, each with a × that takes it out, "Direct" for none; under them the path as the field will get it (OH2RDK-7,OH2RCH-2, DIRECT for none) with the
// count of hops, red with the reason in its title when the field would not take it; and a field to type a hop into (a call with an SSID or an alias, or several separated by commas) with Add, which is off while what is typed is
// no hop or the path is full. The chips have a box of two lines of their own and the count a width of its own, so that what is below does not move as hops come and go.
import { computed, ref } from "vue";
import { t } from "@/i18n";
import { pathOf, typedHops } from "@/lib/pathbuilder";
import { LIMITS } from "@/protocol/lists";

const props = defineProps<{ hops: readonly string[]; problem: string }>();
const emit = defineEmits<{ remove: [index: number]; add: [calls: string[]] }>();

const typed = ref("");
const found = computed(() => typedHops(typed.value));
const room = computed(() => LIMITS.path.maxCalls - props.hops.length);
const addable = computed(() => found.value !== null && found.value.length <= room.value);

function add(): void {
  if (!addable.value || found.value === null) return;
  emit("add", found.value);
  typed.value = "";
}
</script>

<template>
  <div class="pathbuild-path">
    <ol class="pathbuild-hops" :aria-label="t('pathbuilder.hops_label')">
      <li v-if="hops.length === 0" class="pathbuild-direct muted">{{ t("pathbuilder.direct") }}</li>
      <li v-for="(hop, index) in hops" :key="`${index}-${hop}`" class="pathbuild-hop">
        <span v-if="index > 0" class="hop-arrow" aria-hidden="true">→</span>
        <span class="pathbuild-chip">
          <span class="mono">{{ hop }}</span>
          <button
            type="button"
            class="pathbuild-x"
            :aria-label="t('pathbuilder.remove', { call: hop })"
            :title="t('pathbuilder.remove', { call: hop })"
            @click="emit('remove', index)"
          >
            ×
          </button>
        </span>
      </li>
    </ol>
    <p class="pathbuild-result">
      <output class="mono" :class="{ invalid: problem !== '' }" :title="problem || undefined">{{ pathOf(hops) }}</output>
      <span class="pathbuild-count muted">{{ t("pathbuilder.count", { n: hops.length }) }}</span>
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
