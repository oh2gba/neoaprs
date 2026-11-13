<script setup lang="ts">
// The monitor card over the map, opened from the map's menu (components/MapMenu.vue, Monitor): the HF radio's scope larger than the box in Settings, the same waterfall (components/HfWaterfall.vue) over the same receive level
// (components/HfLevelBar.vue). It follows the statistics card (components/StatsCard.vue) in everything: at the bottom right of the map, its cross closes it and so does Esc, whether it is open is remembered by this browser (composables/useAppShell.ts),
// it is dragged by its head or moved with Alt and the arrow keys where moving is on (`movable`: a tablet and a desktop; composables/useFreeDrag.ts) and remembers where it was left, and on a phone it is a card at the bottom of the screen.
// The rows are asked of the daemon while it is there (composables/useScopeLooks.ts counts who looks), and not while the page is hidden.
import { computed, ref } from "vue";
import HfLevelBar from "@/components/HfLevelBar.vue";
import HfWaterfall from "@/components/HfWaterfall.vue";
import IconButton from "@/components/IconButton.vue";
import { useDaemonContext } from "@/composables/useDaemonContext";
import { useFreeDrag } from "@/composables/useFreeDrag";
import { t } from "@/i18n";

const props = withDefaults(defineProps<{ movable?: boolean }>(), { movable: false });
const emit = defineEmits<{ close: [] }>();
const { scope } = useDaemonContext();
const root = ref<HTMLElement | null>(null);
const drag = useFreeDrag(root, "monitorplace", () => props.movable);
const shown = ref(false); // its picture has room (components/HfWaterfall.vue says): on a phone the card stays mounted under a panel tab and shows nothing
scope.look(() => shown.value);
const on = computed(() => scope.wanted.value);
</script>

<template>
  <section
    ref="root"
    class="card monitorcard"
    :class="{ moved: drag.moved.value, movable }"
    :style="drag.style.value"
    :aria-label="t('map.menu.monitor')"
    v-on="drag.on"
  >
    <header class="card-head" :title="movable ? t('station.card.drag_title') : undefined">
      <div class="card-title">
        <span class="card-call"
          ><strong>{{ t("map.menu.monitor") }}</strong></span
        >
      </div>
      <IconButton kind="close" class="card-close" :label="t('iconbutton.close')" @click="emit('close')" />
    </header>
    <div class="card-body">
      <div class="monitor-picture"><HfWaterfall :on="on" @shown="shown = $event" /></div>
      <HfLevelBar :on="on" />
    </div>
  </section>
</template>
