<script setup lang="ts">
// A symbol as a field: the symbol's picture and its name are the control, a click opens the symbol picker (the accessible name is "Change symbol"), and, only for a symbol that can carry one, a small "Letter or digit on it". The symbol is the two characters
// the settings write (the table and the code); the user never sees them. Used by the My station tab, the first-run guide and the Objects form. The guide gives `more`: it has its grid of the common symbols above, so here the symbol in force is plain text and the button
// beside it, "More symbols…", opens the picker. `update:symbol` follows the field as it is changed (the letter is typed);
// `commit` says a symbol is final: one picked from the picker, or the letter when its field is left or Enter is pressed (the My station tab applies it then).
import { computed, nextTick, ref, useId } from "vue";
import InfoTip from "@/components/InfoTip.vue";
import SymbolIcon from "@/components/SymbolIcon.vue";
import { t } from "@/i18n";
import SymbolPicker from "@/components/SymbolPicker.vue";
import { overlayOf, symbolName, tableWithOverlay, takesOverlay } from "@/lib/symbolpicker";

const props = withDefaults(defineProps<{ id: string; symbol: string; label?: string; changed?: boolean; more?: boolean }>(), {
  label: undefined,
  changed: false,
  more: false,
});
const emit = defineEmits<{ "update:symbol": [value: string]; commit: [] }>();

const table = computed(() => props.symbol.slice(0, 1));
const code = computed(() => props.symbol.slice(1, 2));
const name = computed(() => symbolName(table.value, code.value) || t("settings.symbol.none"));
const overlay = computed(() => takesOverlay(table.value, code.value));
const open = ref(false);
const change = ref<HTMLButtonElement | null>(null);
const nameId = useId();

function pick(newTable: string, newCode: string): void {
  // a symbol that takes a letter or a digit keeps the one that was on the symbol before it
  const kept = newTable !== "/" && takesOverlay("\\", newCode) ? overlayOf(table.value) : "";
  emit("update:symbol", `${kept || newTable}${newCode}`);
  emit("commit");
  close();
}

function close(): void {
  open.value = false;
  void nextTick(() => change.value?.focus());
}

function typed(event: Event): void {
  if (event.target instanceof HTMLInputElement) emit("update:symbol", `${tableWithOverlay(event.target.value)}${code.value}`);
}
</script>

<template>
  <div class="field" :class="{ changed }">
    <label :for="`${id}-change`">{{ label ?? t("settings.symbol.label") }}</label>
    <div class="field-control symbolfield">
      <template v-if="more">
        <span class="symbolshown">
          <SymbolIcon :table="table" :code="code" :size="32" />
          <span :id="nameId" class="symbolfield-name">{{ name }}</span>
        </span>
        <button :id="`${id}-change`" ref="change" class="btn symbolmore" type="button" :aria-describedby="nameId" @click="open = true">
          {{ t("settings.symbol.more") }}
        </button>
      </template>
      <button
        v-else
        :id="`${id}-change`"
        ref="change"
        class="symbolbtn"
        type="button"
        :aria-label="t('settings.symbol.change')"
        :aria-describedby="nameId"
        :title="t('settings.symbol.change')"
        @click="open = true"
      >
        <SymbolIcon :table="table" :code="code" :size="32" />
        <span :id="nameId" class="symbolfield-name">{{ name }}</span>
      </button>
      <InfoTip :label="t('settings.about', { label: label ?? t('settings.symbol.label') })" picture="symbol">
        <span class="info-line">{{ t("settings.symbol.tip1") }}</span>
      </InfoTip>
      <label v-if="overlay" class="symbolfield-over muted">
        {{ t("settings.symbol.overlay") }}
        <input
          class="input"
          type="text"
          maxlength="1"
          :value="overlayOf(table)"
          autocomplete="off"
          spellcheck="false"
          @input="typed"
          @change="emit('commit')"
          @keydown.enter="emit('commit')"
        />
      </label>
    </div>
    <SymbolPicker v-if="open" :table="table" :code="code" @pick="pick" @close="close" />
  </div>
</template>
