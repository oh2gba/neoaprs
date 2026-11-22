<script setup lang="ts">
// The menu opened by right-click (long press) on the map: copy the place as decimal degrees or
// as a Maidenhead locator, then Statistics, Packets, Monitor (one per radio that has a scope)
// and Replay. StationMap.vue opens it and handles `close`, `card` (`stats`, `packets`,
// `monitor`) and `replay`. It behaves as every menu of the page (useContextMenu).
import { computed, ref } from "vue";
import { useContextMenu } from "@/composables/useContextMenu";
import type { MapCard } from "@/composables/useMapMenu";
import { useDaemonContext } from "@/composables/useDaemonContext";
import { useRadios } from "@/composables/useRadios";
import { t } from "@/i18n";
import { copyAndSay } from "@/components/copyAndSay";
import { positionToLocator } from "@/lib/locator";
import type { RadioId } from "@/lib/radios";

const props = defineProps<{ lat: number; lon: number; x: number; y: number; trigger: HTMLElement | null }>();
const emit = defineEmits<{ close: []; card: [name: MapCard]; replay: [] }>();
const { say, scope } = useDaemonContext();
const radios = useRadios();

const list = ref<HTMLElement | null>(null);
const buttons = ref<HTMLElement[]>([]);
const menu = useContextMenu({ x: () => props.x, y: () => props.y, trigger: () => props.trigger, list, buttons, close: () => emit("close") });

/** The place as copied: signed decimal degrees to 5 places (about a metre). */
const place = computed(() => `${props.lat.toFixed(5)}, ${props.lon.toFixed(5)}`);
const locator = computed(() => positionToLocator(props.lat, props.lon));

async function copy(text: string): Promise<void> {
  menu.done();
  await copyAndSay(text, say);
}

/** A Monitor item per radio that has a scope, named where several radios are on. */
const monitors = computed(() =>
  scope.radios.value.map((radio) => {
    const name = radios.several.value ? radios.byId(radio)?.name : undefined;
    return { radio, text: name === undefined ? t("map.menu.monitor") : t("radio.line", { name, line: t("map.menu.monitor") }) };
  }),
);

/** An item's place among the buttons, for the arrow keys: the copy items first (the locator is
 * not always there), then Statistics, Packets, the Monitors, Replay. */
const first = computed(() => (locator.value === "" ? 1 : 2));
const at = computed(() => ({ stats: first.value, packets: first.value + 1, monitor: first.value + 2, replay: first.value + 2 + monitors.value.length }));

function choose(item: "stats" | "packets" | "replay"): void {
  menu.done();
  if (item === "replay") emit("replay");
  else emit("card", item);
}

/** The monitor card shows that radio's scope. */
function monitor(radio: RadioId): void {
  menu.done();
  scope.showOnMonitor(radio);
  emit("card", "monitor");
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
    <li role="none">
      <button
        :ref="(el) => (buttons[at.packets] = el as HTMLElement)"
        type="button"
        role="menuitem"
        class="ctxmenu-item"
        tabindex="-1"
        data-item="packets"
        @click="choose('packets')"
      >
        {{ t("tab.packets") }}
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
