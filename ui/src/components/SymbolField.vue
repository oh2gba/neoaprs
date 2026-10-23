<script setup lang="ts">
// A symbol as a field: its picture and its name, a Change button that opens the symbol picker, and, only for a symbol that can carry one, a small "Letter or digit on it". The symbol is the two characters
// the settings write (the table and the code); the user never sees them. Used by the Beacon tab, the first-run guide and the Objects form. `update:symbol` follows the field as it is changed (the letter is typed);
// `commit` says a symbol is final: one picked from the picker, or the letter when its field is left or Enter is pressed (the Beacon tab applies it then).
import { computed, nextTick, ref } from "vue";
import SymbolIcon from "@/components/SymbolIcon.vue";
import SymbolPicker from "@/components/SymbolPicker.vue";
import { overlayOf, symbolName, tableWithOverlay, takesOverlay } from "@/lib/symbolpicker";

const props = withDefaults(defineProps<{ id: string; symbol: string; label?: string; button?: string; changed?: boolean }>(), {
  label: "Symbol",
  button: "Change",
  changed: false,
});
const emit = defineEmits<{ "update:symbol": [value: string]; commit: [] }>();

const table = computed(() => props.symbol.slice(0, 1));
const code = computed(() => props.symbol.slice(1, 2));
const name = computed(() => symbolName(table.value, code.value) || "No symbol");
const overlay = computed(() => takesOverlay(table.value, code.value));
const open = ref(false);
const change = ref<HTMLButtonElement | null>(null);

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
    <label :for="`${id}-change`">{{ label }}</label>
    <div class="field-control symbolfield">
      <SymbolIcon :table="table" :code="code" :size="32" />
      <span class="symbolfield-name">{{ name }}</span>
      <button :id="`${id}-change`" ref="change" class="btn" type="button" @click="open = true">{{ button }}</button>
      <label v-if="overlay" class="symbolfield-over muted">
        Letter or digit on it
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
