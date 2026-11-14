<script setup lang="ts">
// The monitor card over the map, opened from the map's menu (components/MapMenu.vue, Monitor): the HF radio's scope larger than the box in Settings, the same waterfall (components/HfWaterfall.vue) over the same receive level
// (components/HfLevelBar.vue). It follows the statistics card (components/StatsCard.vue) in everything: at the bottom right of the map, its cross closes it and so does Esc, whether it is open is remembered by this browser (composables/useAppShell.ts),
// it is dragged by its head or moved with Alt and the arrow keys where moving is on (`movable`: a tablet and a desktop; composables/useFreeDrag.ts) and remembers where it was left, and on a phone it is a card at the bottom of the screen.
// The rows are asked of the daemon while it is there (composables/useScopeLooks.ts counts who looks), and not while the page is hidden. A right-click on the card (a long press on its body, the menu key on its picture, which takes the
// focus) opens its menu (components/MonitorMenu.vue, composables/useMonitorMenu.ts): the speed of its waterfall, remembered by this browser; the menu is put at the end of the page's body, so that nothing over the map covers it.
import { computed, ref } from "vue";
import HfLevelBar from "@/components/HfLevelBar.vue";
import HfWaterfall from "@/components/HfWaterfall.vue";
import IconButton from "@/components/IconButton.vue";
import MonitorMenu from "@/components/MonitorMenu.vue";
import { useDaemonContext } from "@/composables/useDaemonContext";
import { useFreeDrag } from "@/composables/useFreeDrag";
import { useMonitorMenu } from "@/composables/useMonitorMenu";
import { usePersisted } from "@/composables/usePersisted";
import { t } from "@/i18n";
import { SPEEDS } from "@/lib/waterfall";

const props = withDefaults(defineProps<{ movable?: boolean }>(), { movable: false });
const emit = defineEmits<{ close: [] }>();
const { scope } = useDaemonContext();
const root = ref<HTMLElement | null>(null);
const drag = useFreeDrag(root, "monitorplace", () => props.movable);
const shown = ref(false); // its picture has room (components/HfWaterfall.vue says): on a phone the card stays mounted under a panel tab and shows nothing
scope.look(() => shown.value);
const on = computed(() => scope.wanted.value);
const speed = usePersisted("monitorspeed", "normal", SPEEDS);
const picture = ref<HTMLElement | null>(null);
const menu = useMonitorMenu(() => picture.value);
const listeners = { ...drag.on, ...menu.on };
</script>

<template>
  <section
    ref="root"
    class="card monitorcard"
    :class="{ moved: drag.moved.value, movable }"
    :style="drag.style.value"
    :aria-label="t('map.menu.monitor')"
    v-on="listeners"
  >
    <header class="card-head" :title="movable ? t('station.card.drag_title') : undefined">
      <div class="card-title">
        <span class="card-call"
          ><strong>{{ t("map.menu.monitor") }}</strong></span
        >
      </div>
      <IconButton kind="close" class="card-close" :label="t('iconbutton.close')" @click="emit('close')" />
    </header>
    <div class="card-body" v-on="menu.pressOn">
      <div ref="picture" class="monitor-picture" tabindex="0" aria-haspopup="menu"><HfWaterfall :speed="speed" @shown="shown = $event" /></div>
      <HfLevelBar :on="on" />
    </div>
    <Teleport to="body">
      <MonitorMenu v-if="menu.menu.value" :key="menu.key.value" v-bind="menu.menu.value" :speed="speed" @speed="speed = $event" @close="menu.close()" />
    </Teleport>
  </section>
</template>
