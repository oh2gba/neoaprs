<script setup lang="ts">
// The statistics card over the map, opened from the map's menu (components/MapMenu.vue, Statistics): what the page has heard, counted up (lib/stats.ts) in sections of a few lines each, the stations, how far we reach,
// the packets and the radio since the daemon started. It is at the bottom right of the map, clear of the station cards at the left, and moves as the station book, the packets and the status do. Its cross closes it, and so does
// Esc with the station cards; whether it is open is remembered by this browser (composables/useAppShell.ts), so it comes back with the page. On a phone it is a card at the bottom of the screen like the station's.
import { computed } from "vue";
import IconButton from "@/components/IconButton.vue";
import { useDaemonContext } from "@/composables/useDaemonContext";
import { t } from "@/i18n";
import { mapStats } from "@/lib/stats";
import type { PacketRow } from "@/protocol/protocol";

const props = defineProps<{ packets: ReadonlyMap<string, PacketRow> }>();
const emit = defineEmits<{ close: [] }>();
const page = useDaemonContext();

const sections = computed(() =>
  mapStats({
    stations: page.stations.value,
    packets: props.packets,
    status: page.status.value,
    tnc: page.tnc.value,
    igate: page.igate.value,
    map: page.map.value,
    aging: page.aging.value,
    now: page.now.value,
  }),
);
</script>

<template>
  <section class="card statscard" :aria-label="t('stats.label')">
    <header class="card-head">
      <div class="card-title">
        <span class="card-call"
          ><strong>{{ t("stats.title") }}</strong></span
        >
        <span class="muted">{{ t("stats.note") }}</span>
      </div>
      <IconButton kind="close" class="card-close" :label="t('iconbutton.close')" @click="emit('close')" />
    </header>
    <div class="card-body">
      <template v-for="section in sections" :key="section.title">
        <h3 class="stats-section">{{ t(section.title) }}</h3>
        <dl class="card-fields">
          <template v-for="line in section.lines" :key="line.label">
            <dt>{{ t(line.label, line.params) }}</dt>
            <dd>{{ line.value }}</dd>
          </template>
        </dl>
      </template>
    </div>
  </section>
</template>
