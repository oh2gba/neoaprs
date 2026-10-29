<script setup lang="ts">
// The menu of a row of the Stations table, as short as the Packets tab's (CopyMenu): Copy call, Show on map (or its card, for a station with no position) and the QRZ page of a station; the rest a station offers is in its panel
// at the bottom of the tab (StationPanel), which a click on the row opens. It opens where the pointer is (a right-click or a long press), is kept inside the window, takes the focus on its first item, is moved in by Up, Down,
// Home and End, and closed by Esc (the focus goes back to `trigger`), a press outside it, Tab, or an item that was chosen (useContextMenu). The row it is for is `row`; an item is said to the page with one event, the parent does
// it; the QRZ page is a link, which opens in a tab of its own.
import { computed, ref } from "vue";
import { useContextMenu } from "@/composables/useContextMenu";
import { t } from "@/i18n";
import { qrzUrl } from "@/lib/calls";
import { itemLabel, menuItems, type MenuItem } from "@/lib/stations";
import type { StationRow } from "@/protocol/protocol";

const props = defineProps<{ row: StationRow; x: number; y: number; trigger: HTMLElement | null }>();
const emit = defineEmits<{ close: []; show: [call: string]; copy: [call: string] }>();

const list = ref<HTMLElement | null>(null);
const buttons = ref<HTMLElement[]>([]);
const items = computed(() => menuItems(props.row));
const qrz = computed(() => qrzUrl(props.row.call) ?? undefined);
const menu = useContextMenu({ x: () => props.x, y: () => props.y, trigger: () => props.trigger, list, buttons, close: () => emit("close") });

function choose(item: MenuItem): void {
  if (item === "show") emit("show", props.row.call);
  else if (item === "copy") emit("copy", props.row.call);
  menu.done();
}
</script>

<template>
  <ul
    ref="list"
    class="ctxmenu"
    role="menu"
    :aria-label="t('station.menu.label', { call: row.call })"
    :style="{ left: `${menu.at.value.left}px`, top: `${menu.at.value.top}px` }"
    @keydown="menu.onKey"
    @contextmenu.prevent
  >
    <li v-for="(item, index) in items" :key="item" role="none">
      <a
        v-if="item === 'qrz'"
        :ref="(el) => (buttons[index] = el as HTMLElement)"
        class="ctxmenu-item"
        role="menuitem"
        tabindex="-1"
        :href="qrz"
        target="_blank"
        rel="noopener noreferrer"
        :data-item="item"
        @click="menu.done()"
        >{{ itemLabel(item, row, false) }}</a
      >
      <button
        v-else
        :ref="(el) => (buttons[index] = el as HTMLElement)"
        type="button"
        role="menuitem"
        class="ctxmenu-item"
        tabindex="-1"
        :data-item="item"
        @click="choose(item)"
      >
        {{ itemLabel(item, row, false) }}
      </button>
    </li>
  </ul>
</template>
