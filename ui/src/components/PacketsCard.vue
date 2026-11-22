<script setup lang="ts">
// The Packets tab as a card over the map, opened from the map menu.
// It shows the same log as the tab (PacketsLog) and behaves like the statistics card:
// closes with its cross or Esc, can be moved and resized, and is a bottom sheet on a phone.
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
/** The smallest size at which the table of packets stays readable. */
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
