<script setup lang="ts">
// The map's Layers button and its box. The button stands under + and − in their group's look (its place is a control of the map's: lib/layers/control.ts) and has no text on the page, only its name "Layers"; it opens
// the page's popup (composables/usePopup.ts: a press outside or Esc closes it) with a tick row for each layer (composables/useMapLayers.ts): Tracks, ALOHA circle, Locator grid, then under a thin line Aircraft and
// Ships while the station has a source for them, the source's own name after the name where it is a service. Each row has the layer's mark, so the box is the map's legend. A row of things keeps the room of its count
// at one width in tabular figures (`counts`: a number, null for a dash while its source is away, absent for nothing), so that a changing count moves nothing. The rows the box opened with stay while it is open.
import { computed, ref } from "vue";
import { formatNumber, t } from "@/i18n";
import LayerMark from "@/components/LayerMark.vue";
import { usePopup } from "@/composables/usePopup";
import { useMapLayers } from "@/composables/useMapLayers";
import type { LayerName } from "@/lib/layers/sources";
import type { LayerId, LayerRow } from "@/lib/layers/table";

const props = withDefaults(
  defineProps<{
    /** where the button stands among the map's controls; null until the map has its controls */
    place: HTMLElement | null;
    counts?: Partial<Record<LayerName, number | null>>;
  }>(),
  { counts: () => ({}) },
);

const layers = useMapLayers();
const open = ref(false);
const root = ref<HTMLElement | null>(null);
const button = ref<HTMLButtonElement | null>(null);
const opened = ref<LayerRow[]>([]);
const rows = computed(() => (open.value ? opened.value : layers.rows.value));
const popup = usePopup({ open, root, trigger: button, close: () => (open.value = false) });

function toggle(): void {
  opened.value = layers.rows.value;
  open.value = !open.value;
}

/** The thin line goes before the first row of things. */
const ruleBefore = (row: LayerRow, i: number): boolean => row.part === "outside" && rows.value[i - 1]?.part !== "outside";

function countText(id: LayerId): string {
  if (id !== "aircraft" && id !== "ships") return "";
  const count = props.counts[id];
  return count === undefined ? "" : count === null ? "–" : formatNumber(count, 0);
}

const onTick = (id: LayerId, event: Event): void => layers.setTicked(id, (event.target as HTMLInputElement).checked);
</script>

<template>
  <Teleport v-if="place" :to="place">
    <div ref="root" class="layers" @keydown="popup.onEscape">
      <button
        ref="button"
        class="layers-toggle"
        type="button"
        :aria-expanded="open"
        :aria-label="t('layers.box.button')"
        :title="t('layers.box.button')"
        @click="toggle"
      >
        <LayerMark name="layers" />
      </button>
      <div v-if="open" class="layers-box" role="group" :aria-label="t('layers.box.button')">
        <template v-for="(row, i) in rows" :key="row.id">
          <hr v-if="ruleBefore(row, i)" class="layers-rule" />
          <label class="check layers-row" :data-layer="row.id">
            <input type="checkbox" :checked="layers.ticked(row.id)" @change="onTick(row.id, $event)" />
            <LayerMark :name="row.mark" />
            <span class="layers-name">{{ t(row.name) }}</span>
            <span v-if="row.source" class="layers-source">{{ row.source }}</span>
            <span v-if="row.part === 'outside'" class="layers-count">{{ countText(row.id) }}</span>
          </label>
        </template>
      </div>
    </div>
  </Teleport>
</template>
