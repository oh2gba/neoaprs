<script setup lang="ts">
// The monitor card's menu (components/MonitorCard.vue), opened by a right-click on the card, a long press on its body or the menu key on the picture: the speed of its waterfall, Slow, Normal or Fast, the one that is on with a
// check mark in a column every item keeps, so that choosing moves no word (lib/waterfall.ts PACE says what a speed is). It opens where the pointer is and is kept inside the window, takes the focus on its first item, is moved in
// with the arrow keys and closed by Esc (the focus goes back to the picture), a press outside it or an item that was chosen (useContextMenu), as every menu of the page. The card opens it (useMonitorMenu) and hears `speed` and `close`.
import { ref } from "vue";
import { useContextMenu } from "@/composables/useContextMenu";
import { t } from "@/i18n";
import { SPEEDS, type Speed } from "@/lib/waterfall";

const props = defineProps<{ speed: Speed; x: number; y: number; trigger: HTMLElement | null }>();
const emit = defineEmits<{ close: []; speed: [speed: Speed] }>();

const list = ref<HTMLElement | null>(null);
const buttons = ref<HTMLElement[]>([]);
const menu = useContextMenu({ x: () => props.x, y: () => props.y, trigger: () => props.trigger, list, buttons, close: () => emit("close") });

function label(speed: Speed): string {
  switch (speed) {
    case "slow":
      return t("map.monitor.speed_slow");
    case "normal":
      return t("map.monitor.speed_normal");
    case "fast":
      return t("map.monitor.speed_fast");
  }
}

/** Tab leaves the menu from the picture, so that the browser moves on to what comes after the card: the menu itself stands at the end of the page. */
function onKey(event: KeyboardEvent): void {
  if (event.key === "Tab") props.trigger?.focus();
  menu.onKey(event);
}

function choose(speed: Speed): void {
  menu.done();
  emit("speed", speed);
}
</script>

<template>
  <ul
    ref="list"
    class="ctxmenu monitormenu"
    role="menu"
    :aria-label="t('map.menu.monitor')"
    :style="{ left: `${menu.at.value.left}px`, top: `${menu.at.value.top}px` }"
    @keydown="onKey"
    @contextmenu.prevent
  >
    <li role="none">
      <div id="monitormenu-speed" class="ctxmenu-title">{{ t("map.monitor.speed") }}</div>
      <ul class="ctxmenu-group" role="group" aria-labelledby="monitormenu-speed">
        <li v-for="(each, index) in SPEEDS" :key="each" role="none">
          <button
            :ref="(el) => (buttons[index] = el as HTMLElement)"
            type="button"
            role="menuitemradio"
            :aria-checked="each === speed ? 'true' : 'false'"
            class="ctxmenu-item"
            tabindex="-1"
            :data-speed="each"
            @click="choose(each)"
          >
            <span class="ctxmenu-mark" aria-hidden="true">&#10003;</span>{{ label(each) }}
          </button>
        </li>
      </ul>
    </li>
  </ul>
</template>
