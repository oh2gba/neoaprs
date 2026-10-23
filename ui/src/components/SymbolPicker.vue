<script setup lang="ts">
// The symbol picker: every symbol of the APRS set as a picture with its name, the usual ones first, searchable by words ("house", "car", "digi", "wx"). A click on a symbol chooses it and closes the picker;
// Esc, the Close button or a click outside closes it without a choice. The symbol now in use is marked. It says nothing of tables and codes: the choice is the table and the code, written as the settings write them.
import { computed, onMounted, ref } from "vue";
import SymbolIcon from "@/components/SymbolIcon.vue";
import { ALL_SYMBOLS, filterSymbols, symbolName, type PickSymbol } from "@/lib/symbolpicker";
import { SYMBOL_CHOICES } from "@/lib/setup";

const props = defineProps<{ table: string; code: string }>();
const emit = defineEmits<{ pick: [table: string, code: string]; close: [] }>();

const query = ref("");
const search = ref<HTMLInputElement | null>(null);
const usual = computed<PickSymbol[]>(() => SYMBOL_CHOICES.map((s) => ({ table: s.table, code: s.code, name: symbolName(s.table, s.code) || s.name })));
const found = computed(() => filterSymbols(ALL_SYMBOLS, query.value));
const searching = computed(() => query.value.trim() !== "");
/** The symbol in use: an overlay table is the alternate table with a character over it. */
const current = (s: PickSymbol): boolean => s.code === props.code && (s.table === "/" ? props.table === "/" : props.table !== "/");

onMounted(() => search.value?.focus());
</script>

<template>
  <div class="picker-backdrop" @pointerdown.self="emit('close')" @keydown.esc.stop="emit('close')">
    <div class="picker" role="dialog" aria-modal="true" aria-label="Choose a symbol">
      <div class="picker-head">
        <input
          ref="search"
          v-model="query"
          class="input"
          type="search"
          placeholder="Search: house, car, digi, wx..."
          aria-label="Search symbols"
          autocomplete="off"
          spellcheck="false"
        />
        <button class="btn" type="button" @click="emit('close')">Close</button>
      </div>
      <div class="picker-body">
        <template v-if="!searching">
          <h3>Usual</h3>
          <div class="picker-grid" role="group" aria-label="Usual symbols">
            <button
              v-for="s in usual"
              :key="s.table + s.code"
              type="button"
              class="picker-symbol"
              :class="{ active: current(s) }"
              :aria-pressed="current(s)"
              @click="emit('pick', s.table, s.code)"
            >
              <SymbolIcon :table="s.table" :code="s.code" :size="32" />
              <span>{{ s.name }}</span>
            </button>
          </div>
          <h3>All</h3>
        </template>
        <div class="picker-grid" role="group" aria-label="All symbols">
          <button
            v-for="s in found"
            :key="s.table + s.code"
            type="button"
            class="picker-symbol"
            :class="{ active: current(s) }"
            :aria-pressed="current(s)"
            @click="emit('pick', s.table, s.code)"
          >
            <SymbolIcon :table="s.table" :code="s.code" :size="32" />
            <span>{{ s.name }}</span>
          </button>
        </div>
        <p v-if="found.length === 0" class="empty">No symbol like that.</p>
      </div>
    </div>
  </div>
</template>
