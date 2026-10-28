<script setup lang="ts">
// The menu a right-click (a long press on a touch screen) opens on the map itself, where the pointer is: the place under it to copy as decimal degrees ("Copy position 60.17000, 24.94000") or as a Maidenhead locator
// ("Copy locator KP20le"), and last, under a line, Statistics, which opens the statistics card over the map (components/StatsCard.vue). A copy puts the text on the clipboard and the page says so in its toast. The menu
// is kept inside the window, takes the focus, is moved in with the arrow keys and closed by Esc, a press outside it or an item that was chosen (useContextMenu). The map opens it (components/StationMap.vue) and hears `close` and `stats`.
import { computed, ref } from "vue";
import { useContextMenu } from "@/composables/useContextMenu";
import { useDaemonContext } from "@/composables/useDaemonContext";
import { t } from "@/i18n";
import { copyText } from "@/lib/clipboard";
import { saidText } from "@/lib/copy";
import { positionToLocator } from "@/lib/locator";

const props = defineProps<{ lat: number; lon: number; x: number; y: number; trigger: HTMLElement | null }>();
const emit = defineEmits<{ close: []; stats: [] }>();
const { say } = useDaemonContext();

const list = ref<HTMLElement | null>(null);
const buttons = ref<HTMLElement[]>([]);
const menu = useContextMenu({ x: () => props.x, y: () => props.y, trigger: () => props.trigger, list, buttons, close: () => emit("close") });

/** The place as it is copied: signed decimal degrees to 5 places (about a metre), the way other programs take them. */
const place = computed(() => `${props.lat.toFixed(5)}, ${props.lon.toFixed(5)}`);
const locator = computed(() => positionToLocator(props.lat, props.lon));

async function copy(text: string): Promise<void> {
  menu.done();
  if (await copyText(text)) say(t("copy.copied", { text: saidText(text) }));
}

function stats(): void {
  menu.done();
  emit("stats");
}
</script>

<template>
  <ul
    ref="list"
    class="ctxmenu mapmenu"
    role="menu"
    :aria-label="t('map.menu_label')"
    :style="{ left: `${menu.at.value.left}px`, top: `${menu.at.value.top}px` }"
    @keydown="menu.onKey"
    @contextmenu.prevent
  >
    <li role="none">
      <button
        :ref="(el) => (buttons[0] = el as HTMLElement)"
        type="button"
        role="menuitem"
        class="ctxmenu-item"
        tabindex="-1"
        data-item="position"
        @click="copy(place)"
      >
        {{ t("map.menu.copy_position", { place }) }}
      </button>
    </li>
    <li v-if="locator !== ''" role="none">
      <button
        :ref="(el) => (buttons[1] = el as HTMLElement)"
        type="button"
        role="menuitem"
        class="ctxmenu-item"
        tabindex="-1"
        data-item="locator"
        @click="copy(locator)"
      >
        {{ t("map.menu.copy_locator", { locator }) }}
      </button>
    </li>
    <li class="ctxmenu-line" role="separator"></li>
    <li role="none">
      <button
        :ref="(el) => (buttons[locator === '' ? 1 : 2] = el as HTMLElement)"
        type="button"
        role="menuitem"
        class="ctxmenu-item"
        tabindex="-1"
        data-item="stats"
        @click="stats"
      >
        {{ t("map.menu.stats") }}
      </button>
    </li>
  </ul>
</template>
