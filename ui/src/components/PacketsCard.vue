<script setup lang="ts">
// The Packets tab as a card over the map, opened from the map's menu (components/MapMenu.vue, Packets): the tab's own log (components/PacketsLog.vue, the same component on the same packets: its filter, its lines,
// its click and its right-click), every radio's and the internet's packets decoded, where a Monitor card is one radio's signal. Its head has the tab's own name. It follows the statistics card (components/StatsCard.vue)
// in everything: at the bottom right of the map, beside the statistics card where both are open, its cross closes it and so does Esc, whether it is open is remembered by this browser (composables/useAppShell.ts), it is
// dragged by its head or moved with Alt and the arrow keys where moving is on (`movable`: a tablet and a desktop; composables/useFreeDrag.ts) and remembers where it was left, and on a phone it is a card at the bottom
// of the screen. It has a height of its own, so that it does not grow as the packets come.
import { ref } from "vue";
import IconButton from "@/components/IconButton.vue";
import PacketsLog from "@/components/PacketsLog.vue";
import { useFreeDrag } from "@/composables/useFreeDrag";
import { t } from "@/i18n";
import type { PacketRow } from "@/protocol/protocol";

const props = withDefaults(defineProps<{ packets: ReadonlyMap<string, PacketRow>; movable?: boolean }>(), { movable: false });
const emit = defineEmits<{ close: [] }>();
const root = ref<HTMLElement | null>(null);
const drag = useFreeDrag(root, "packetsplace", () => props.movable);
</script>

<template>
  <section
    ref="root"
    class="card packetscard"
    :class="{ moved: drag.moved.value, movable }"
    :style="drag.style.value"
    :aria-label="t('packets.card_label')"
    v-on="drag.on"
  >
    <header class="card-head" :title="movable ? t('station.card.drag_title') : undefined">
      <div class="card-title">
        <span class="card-call"
          ><strong>{{ t("tab.packets") }}</strong></span
        >
      </div>
      <IconButton kind="close" class="card-close" :label="t('iconbutton.close')" @click="emit('close')" />
    </header>
    <div class="card-body">
      <PacketsLog :packets="packets" />
    </div>
  </section>
</template>
