<script setup lang="ts">
// The Packets tab as a card over the map, opened from the map's menu (components/MapMenu.vue, Packets): the tab's own log (components/PacketsLog.vue, the same component on the same packets: its filter, its lines,
// its click and its right-click), every radio's and the internet's packets decoded, where a Monitor card is one radio's signal. Its head has the tab's own name. It follows the statistics card (components/StatsCard.vue)
// in everything: at the bottom right of the map, beside the statistics card where both are open, its cross closes it and so does Esc, whether it is open is remembered by this browser (composables/useAppShell.ts), it is
// dragged by its head or moved with Alt and the arrow keys where moving is on (`movable`: a tablet and a desktop; composables/useFreeDrag.ts) and remembers where it was left, and on a phone it is a card at the bottom
// of the screen. It has a height of its own, so that it does not grow as the packets come; its edges and corners size it, or Ctrl and Alt with the arrow keys, and it remembers its size too (composables/useCardSize.ts).
import { ref } from "vue";
import CardSizer from "@/components/CardSizer.vue";
import IconButton from "@/components/IconButton.vue";
import PacketsLog from "@/components/PacketsLog.vue";
import { SIZE_KEYS, useCardSize } from "@/composables/useCardSize";
import { useFreeDrag } from "@/composables/useFreeDrag";
import { t } from "@/i18n";
import type { PacketRow } from "@/protocol/protocol";

const props = withDefaults(defineProps<{ packets: ReadonlyMap<string, PacketRow>; movable?: boolean }>(), { movable: false });
const emit = defineEmits<{ close: [] }>();
const root = ref<HTMLElement | null>(null);
const drag = useFreeDrag(root, "packetsplace", () => props.movable);
/** The least the table of packets can be read at. */
const LEAST = { width: 380, height: 240 };
const sizing = useCardSize(root, "packetssize", LEAST, drag, () => props.movable);
const listeners = { ...drag.on, keydown: (event: KeyboardEvent) => (drag.on.keydown(event), sizing.keydown(event)) };
</script>

<template>
  <section
    ref="root"
    class="card packetscard"
    :class="{ moved: drag.moved.value, movable, sized: sizing.sized.value }"
    :style="{ ...drag.style.value, ...sizing.style.value }"
    :aria-keyshortcuts="movable ? SIZE_KEYS : undefined"
    :aria-label="t('packets.card_label')"
    v-on="listeners"
  >
    <header class="card-head" :title="movable ? t('station.card.size_title') : undefined">
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
    <CardSizer :sizing="sizing" />
  </section>
</template>
