<script setup lang="ts">
// Step 3 of the first-run guide: the symbol the station is drawn with: the 12 most common ones from the sprite, or any other from the picker, which has them all and which "More symbols…" opens; the symbol in force is shown under the grid, beside that button (the symbol control of the Beacon tab, SymbolField with `more`).
import SymbolField from "@/components/SymbolField.vue";
import SymbolButton from "@/components/SymbolButton.vue";
import { t } from "@/i18n";
import { useDaemonContext } from "@/composables/useDaemonContext";
import { SYMBOL_CHOICES } from "@/lib/setup";

const { guide } = useDaemonContext();
</script>

<template>
  <div class="setup-symbols" role="group" :aria-label="t('setup.symbols')">
    <SymbolButton
      v-for="s in SYMBOL_CHOICES"
      :key="s.table + s.code"
      class="setup-symbol"
      :table="s.table"
      :code="s.code"
      :name="s.name"
      :active="guide.fields.symbol === s.table + s.code"
      @pick="guide.edit('symbol', s.table + s.code)"
    />
  </div>
  <SymbolField id="setup-symbol" :symbol="guide.fields.symbol" more @update:symbol="guide.edit('symbol', $event)" />
</template>
