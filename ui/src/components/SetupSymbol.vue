<script setup lang="ts">
// Step 3 of the first-run guide: the symbol the station is drawn with: the 12 most common ones from the sprite, or any other from the picker (More...), which has them all.
import SymbolField from "@/components/SymbolField.vue";
import SymbolIcon from "@/components/SymbolIcon.vue";
import type { SetupGuide } from "@/composables/useSetupGuide";
import { SYMBOL_CHOICES } from "@/lib/setup";

const props = defineProps<{ guide: SetupGuide }>();
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
  <SymbolField id="setup-symbol" :symbol="props.guide.fields.symbol" button="More..." @update:symbol="props.guide.edit('symbol', $event)" />
</template>
