<script setup lang="ts">
// The card of a satellite on the map, in the station cards' row (StationCards.vue), in the look of
// an aircraft's card (LayerCard.vue): mark, name and kind in the head, then the rows of
// lib/layers/satellitecard.ts, the path as a field to copy, and with a pass the table of where to
// tune at its rise, highest point and set. The label column keeps the room of the widest label and
// the figures are tabular, so nothing moves as the pass begins or the Doppler changes. Several may
// be open; it cannot be pinned or dragged.
import { computed } from "vue";
import CopyField from "@/components/CopyField.vue";
import IconButton from "@/components/IconButton.vue";
import LayerMark from "@/components/LayerMark.vue";
import { t } from "@/i18n";
import { satelliteLabels, satelliteRows, tuneRows } from "@/lib/layers/satellitecard";
import type { SatelliteCard } from "@/protocol/protocol";

const props = defineProps<{ card: SatelliteCard; now: number }>();
const emit = defineEmits<{ close: [] }>();

const rows = computed(() => satelliteRows(props.card, props.now));
const labels = computed(() => satelliteLabels());
const tunes = computed(() => tuneRows(props.card));
</script>

<template>
  <section class="card layercard satcard" :aria-label="t('layers.sat.kind')" :data-satellite="card.id">
    <header class="card-head">
      <span class="layercard-mark"><LayerMark name="satellite" /></span>
      <div class="card-title">
        <span class="card-call">
          <strong>{{ card.name }}</strong>
        </span>
        <span class="muted">{{ t("layers.sat.kind") }}</span>
      </div>
      <IconButton kind="close" class="card-close" :label="t('iconbutton.close')" @click="emit('close')" />
    </header>
    <div class="card-body">
      <dl class="card-fields">
        <dt class="layercard-room" aria-hidden="true">
          <span v-for="label in labels" :key="label">{{ label }}</span>
        </dt>
        <dd class="layercard-room"></dd>
        <template v-for="(row, i) in rows" :key="`${i}:${row.label}`">
          <dt>{{ row.label }}</dt>
          <dd>{{ row.text }}</dd>
        </template>
        <template v-if="card.path">
          <dt>{{ t("station.field.path") }}</dt>
          <dd><CopyField :text="card.path" /></dd>
        </template>
      </dl>
      <table v-if="tunes.length > 0" class="satcard-tune">
        <thead>
          <tr>
            <th scope="col">MHz</th>
            <th scope="col">{{ t("layers.sat.rise") }}</th>
            <th scope="col">{{ t("layers.sat.highest") }}</th>
            <th scope="col">{{ t("layers.sat.set") }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(row, i) in tunes" :key="i">
            <th scope="row">{{ row.label }}</th>
            <td v-for="(cell, j) in row.cells" :key="j">{{ cell }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>
