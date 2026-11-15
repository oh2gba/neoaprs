<script setup lang="ts">
// The menu a right-click (a long press on a touch screen) opens on the map itself, where the pointer is: the place under it to copy as decimal degrees ("Copy position 60.17000, 24.94000") or as a Maidenhead locator
// ("Copy locator KP20le"), and last, under a line, Statistics, which opens the statistics card over the map (components/StatsCard.vue), Monitor, which opens a radio's scope as a card over the map (components/MonitorCard.vue; one for each radio that has a scope now, none without, each with its radio's name where several radios are on: "20 m: Monitor"), and Replay, which plays back how the stations moved (components/ReplayBar.vue). A copy puts the text on the clipboard and the page says so in its toast. The menu
// is kept inside the window, takes the focus, is moved in with the arrow keys and closed by Esc, a press outside it or an item that was chosen (useContextMenu). The map opens it (components/StationMap.vue) and hears `close`, `stats`, `monitor` and `replay`.
import { computed, ref } from "vue";
import { useContextMenu } from "@/composables/useContextMenu";
import { useDaemonContext } from "@/composables/useDaemonContext";
import { useRadios } from "@/composables/useRadios";
import { t } from "@/i18n";
import { copyAndSay } from "@/components/copyAndSay";
import { positionToLocator } from "@/lib/locator";
import type { RadioId } from "@/lib/radios";

const props = defineProps<{ lat: number; lon: number; x: number; y: number; trigger: HTMLElement | null }>();
const emit = defineEmits<{ close: []; stats: []; monitor: []; replay: [] }>();
const { say, scope } = useDaemonContext();
const radios = useRadios();

const list = ref<HTMLElement | null>(null);
const buttons = ref<HTMLElement[]>([]);
const menu = useContextMenu({ x: () => props.x, y: () => props.y, trigger: () => props.trigger, list, buttons, close: () => emit("close") });

/** The place as it is copied: signed decimal degrees to 5 places (about a metre), the way other programs take them. */
const place = computed(() => `${props.lat.toFixed(5)}, ${props.lon.toFixed(5)}`);
const locator = computed(() => positionToLocator(props.lat, props.lon));

async function copy(text: string): Promise<void> {
  menu.done();
  await copyAndSay(text, say);
}

/** A Monitor for each radio that has a scope, with its name where several radios are on. */
const monitors = computed(() =>
  scope.radios.value.map((radio) => {
    const name = radios.several.value ? radios.byId(radio)?.name : undefined;
    return { radio, text: name === undefined ? t("map.menu.monitor") : t("radio.line", { name, line: t("map.menu.monitor") }) };
  }),
);

/** The place of an item among the buttons, for the arrow keys: the two to copy come first (the locator is not always there), then Statistics, the Monitors, Replay. */
const first = computed(() => (locator.value === "" ? 1 : 2));
const at = computed(() => ({ stats: first.value, monitor: first.value + 1, replay: first.value + 1 + monitors.value.length }));

function choose(item: "stats" | "replay"): void {
  menu.done();
  if (item === "stats") emit("stats");
  else emit("replay");
}

/** The monitor card shows that radio's scope. */
function monitor(radio: RadioId): void {
  menu.done();
  scope.showOnMonitor(radio);
  emit("monitor");
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
        :ref="(el) => (buttons[at.stats] = el as HTMLElement)"
        type="button"
        role="menuitem"
        class="ctxmenu-item"
        tabindex="-1"
        data-item="stats"
        @click="choose('stats')"
      >
        {{ t("map.menu.stats") }}
      </button>
    </li>
    <li v-for="(item, i) in monitors" :key="item.radio" role="none">
      <button
        :ref="(el) => (buttons[at.monitor + i] = el as HTMLElement)"
        type="button"
        role="menuitem"
        class="ctxmenu-item"
        tabindex="-1"
        data-item="monitor"
        :data-radio="item.radio"
        @click="monitor(item.radio)"
      >
        {{ item.text }}
      </button>
    </li>
    <li role="none">
      <button
        :ref="(el) => (buttons[at.replay] = el as HTMLElement)"
        type="button"
        role="menuitem"
        class="ctxmenu-item"
        tabindex="-1"
        data-item="replay"
        @click="choose('replay')"
      >
        {{ t("map.menu.replay") }}
      </button>
    </li>
  </ul>
</template>
