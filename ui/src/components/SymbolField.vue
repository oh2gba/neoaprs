<script setup lang="ts">
// A symbol as a field: its picture and name open the symbol picker ("Change symbol"); a symbol
// that can carry one also shows a "Letter or digit on it" field. The symbol is the table and
// code characters the settings write. With `more` (setup guide) the symbol is plain text and
// a "More symbols…" button opens the picker. `update:symbol` follows each edit; `commit` marks
// a final symbol: picked, or the letter after blur or Enter.
import { computed, nextTick, ref, useId } from "vue";
import InfoTip from "@/components/InfoTip.vue";
import SymbolIcon from "@/components/SymbolIcon.vue";
import { t } from "@/i18n";
import SymbolPicker from "@/components/SymbolPicker.vue";
import { confirms } from "@/lib/ime";
import { overlayOf, symbolName, tableWithOverlay, takesOverlay } from "@/lib/symbolpicker";

const props = withDefaults(
  defineProps<{ id: string; symbol: string; label?: string; changed?: boolean; more?: boolean }>(),
  {
    label: undefined,
    changed: false,
    more: false,
  },
);
const emit = defineEmits<{ "update:symbol": [value: string]; commit: [] }>();

function enter(event: KeyboardEvent): void {
  if (confirms(event)) emit("commit");
}

const table = computed(() => props.symbol.slice(0, 1));
const code = computed(() => props.symbol.slice(1, 2));
const name = computed(() => symbolName(table.value, code.value) || t("settings.symbol.none"));
const overlay = computed(() => takesOverlay(table.value, code.value));
const open = ref(false);
const change = ref<HTMLButtonElement | null>(null);
const nameId = useId();
const labelId = useId();

function pick(newTable: string, newCode: string): void {
  // Keep the earlier letter or digit on a symbol that takes one.
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
  if (event.target instanceof HTMLInputElement)
    emit("update:symbol", `${tableWithOverlay(event.target.value)}${code.value}`);
}
</script>

<template>
  <div class="field" :class="{ changed }">
    <label :id="labelId" :for="`${id}-change`">{{ label ?? t("settings.symbol.label") }}</label>
    <div class="field-control symbolfield">
      <template v-if="more">
        <span class="symbolshown">
          <SymbolIcon :table="table" :code="code" :size="32" />
          <span :id="nameId" class="symbolfield-name">{{ name }}</span>
        </span>
        <button
          :id="`${id}-change`"
          ref="change"
          class="btn symbolmore"
          type="button"
          :aria-describedby="nameId"
          @click="open = true"
        >
          {{ t("settings.symbol.more") }}
        </button>
      </template>
      <button
        v-else
        :id="`${id}-change`"
        ref="change"
        class="symbolbtn"
        type="button"
        :aria-labelledby="`${labelId} ${nameId}`"
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
          @keydown.enter="enter"
        />
      </label>
    </div>
    <SymbolPicker v-if="open" :table="table" :code="code" @pick="pick" @close="close" />
  </div>
</template>
