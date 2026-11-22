<script setup lang="ts">
// The monitor card over the map, opened from the map menu (MapMenu.vue): a radio's scope larger
// than Settings', the same waterfall (HfWaterfall.vue) over the same receive level
// (HfLevelBar.vue). It follows the statistics card (StatsCard.vue): closed by its cross or Esc,
// open state remembered by this browser, draggable and sizable (useFreeDrag.ts, useCardSize.ts)
// with position and size remembered. Rows are requested from the daemon while it is shown
// (useScopeLooks.ts). Right-click opens its menu (MonitorMenu.vue). Its radio is the one chosen
// in the map menu while it has a scope, else the first that has one.
import { computed, ref } from "vue";
import CardSizer from "@/components/CardSizer.vue";
import HfLevelBar from "@/components/HfLevelBar.vue";
import HfWaterfall from "@/components/HfWaterfall.vue";
import IconButton from "@/components/IconButton.vue";
import MonitorMenu from "@/components/MonitorMenu.vue";
import { SIZE_KEYS, useCardSize } from "@/composables/useCardSize";
import { useDaemonContext } from "@/composables/useDaemonContext";
import { useFreeDrag } from "@/composables/useFreeDrag";
import { useMonitorMenu } from "@/composables/useMonitorMenu";
import { usePersisted } from "@/composables/usePersisted";
import { useRadios } from "@/composables/useRadios";
import { t } from "@/i18n";
import { SPEEDS } from "@/lib/waterfall";

const props = withDefaults(defineProps<{ movable?: boolean }>(), { movable: false });
const emit = defineEmits<{ close: [] }>();
const { scope } = useDaemonContext();
const radios = useRadios();
const root = ref<HTMLElement | null>(null);
const drag = useFreeDrag(root, "monitorplace", () => props.movable);
/** The least size at which the picture, its level and the head can be read. */
const LEAST = { width: 340, height: 300 };
const sizing = useCardSize(root, "monitorsize", LEAST, drag, () => props.movable);
const shown = ref(false); // its picture has room (HfWaterfall.vue says); mounted but empty under a phone panel tab
const radio = computed(() => scope.monitor.value);
scope.look(
  () => shown.value,
  () => radio.value,
);
const on = computed(() => radio.value !== null && scope.asked.value.includes(radio.value));
/** The card's name: with the radio's where several radios are on. */
const title = computed(() => {
  const id = radio.value;
  const name = id === null || !radios.several.value ? undefined : radios.byId(id)?.name;
  return name === undefined ? t("map.menu.monitor") : t("radio.line", { name, line: t("map.menu.monitor") });
});
const speed = usePersisted("monitorspeed", "normal", SPEEDS);
const picture = ref<HTMLElement | null>(null);
const menu = useMonitorMenu(() => picture.value);
const listeners = { ...drag.on, ...menu.on, keydown: (event: KeyboardEvent) => (drag.on.keydown(event), sizing.keydown(event)) };
</script>

<template>
  <section
    ref="root"
    class="card monitorcard"
    :class="{ moved: drag.moved.value, movable, sized: sizing.sized.value }"
    :style="{ ...drag.style.value, ...sizing.style.value }"
    :aria-keyshortcuts="movable ? SIZE_KEYS : undefined"
    :aria-label="title"
    v-on="listeners"
  >
    <header class="card-head" :title="movable ? t('station.card.size_title') : undefined">
      <div class="card-title">
        <span class="card-call"
          ><strong>{{ title }}</strong></span
        >
      </div>
      <IconButton kind="close" class="card-close" :label="t('iconbutton.close')" @click="emit('close')" />
    </header>
    <div class="card-body" v-on="menu.pressOn">
      <div ref="picture" class="monitor-picture" tabindex="0" aria-haspopup="menu"><HfWaterfall :speed="speed" :radio="radio" @shown="shown = $event" /></div>
      <HfLevelBar :on="on" :radio="radio" />
    </div>
    <CardSizer :sizing="sizing" />
    <Teleport to="body">
      <MonitorMenu v-if="menu.menu.value" :key="menu.key.value" v-bind="menu.menu.value" :speed="speed" @speed="speed = $event" @close="menu.close()" />
    </Teleport>
  </section>
</template>
