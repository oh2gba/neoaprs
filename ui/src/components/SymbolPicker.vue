<script setup lang="ts">
// The symbol picker: every symbol of the APRS set as a picture with its name, the usual ones first, searchable by words ("house", "car", "digi", "wx"). A click on a symbol chooses it and closes the picker;
// Esc, the Close button or a click outside closes it without a choice. The symbol now in use is marked. It says nothing of tables and codes: the choice is the table and the code, written as the settings write them.
import { computed, onMounted, ref } from "vue";
import SymbolButton from "@/components/SymbolButton.vue";
import { t } from "@/i18n";
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
  <div class="sympick-backdrop" @pointerdown.self="emit('close')" @keydown.esc.stop="emit('close')">
    <div class="sympick" role="dialog" aria-modal="true" :aria-label="t('settings.picker.title')">
      <div class="sympick-head">
        <input
          ref="search"
          v-model="query"
          class="input"
          type="search"
          :placeholder="t('settings.picker.placeholder')"
          :aria-label="t('settings.picker.search')"
          autocomplete="off"
          spellcheck="false"
        />
        <button class="btn" type="button" @click="emit('close')">{{ t("settings.picker.close") }}</button>
      </div>
      <div class="sympick-body">
        <template v-if="!searching">
          <h3>{{ t("settings.picker.usual") }}</h3>
          <div class="sympick-grid" role="group" :aria-label="t('settings.picker.usual_symbols')">
            <SymbolButton
              v-for="s in usual"
              :key="s.table + s.code"
              class="sympick-symbol"
              :table="s.table"
              :code="s.code"
              :name="s.name"
              :active="current(s)"
              @pick="emit('pick', s.table, s.code)"
            />
          </div>
          <h3>{{ t("settings.picker.all") }}</h3>
        </template>
        <div class="sympick-grid" role="group" :aria-label="t('settings.picker.all_symbols')">
          <SymbolButton
            v-for="s in found"
            :key="s.table + s.code"
            class="sympick-symbol"
            :table="s.table"
            :code="s.code"
            :name="s.name"
            :active="current(s)"
            @pick="emit('pick', s.table, s.code)"
          />
        </div>
        <p v-if="found.length === 0" class="empty">{{ t("settings.picker.none") }}</p>
      </div>
    </div>
  </div>
</template>
