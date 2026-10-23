<script setup lang="ts">
// Step 3 of the first-run guide: the symbol the station is drawn with: the 12 most common ones from the sprite, or any table and code typed (`/-`, `\k`, `S#`).
import SettingsField from "@/components/SettingsField.vue";
import SymbolIcon from "@/components/SymbolIcon.vue";
import type { SetupGuide } from "@/composables/useSetupGuide";
import { SYMBOL_CHOICES } from "@/lib/setup";

const props = defineProps<{ guide: SetupGuide }>();
const info = { label: "Symbol", empty: "/-", title: "Table and code: / primary, \\ alternate, 0-9 and A-Z overlay" };
</script>

<template>
  <div class="setup-symbols" role="group" aria-label="Symbols">
    <button
      v-for="s in SYMBOL_CHOICES"
      :key="s.table + s.code"
      type="button"
      class="setup-symbol"
      :class="{ active: props.guide.fields.symbol === s.table + s.code }"
      :aria-pressed="props.guide.fields.symbol === s.table + s.code"
      @click="props.guide.edit('symbol', s.table + s.code)"
    >
      <SymbolIcon :table="s.table" :code="s.code" :size="32" />
      <span>{{ s.name }}</span>
    </button>
  </div>
  <SettingsField
    id="setup-symbol"
    :info="info"
    :model-value="props.guide.fields.symbol"
    fallback=""
    :error="props.guide.problems.symbol ?? ''"
    :changed="false"
    @update:model-value="props.guide.edit('symbol', $event)"
  >
    <template #after>
      <SymbolIcon :table="props.guide.fields.symbol.slice(0, 1)" :code="props.guide.fields.symbol.slice(1)" :size="28" />
    </template>
  </SettingsField>
</template>
