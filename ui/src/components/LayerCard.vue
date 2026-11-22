<script setup lang="ts">
// The card of an aircraft or a ship on the map, in the station cards' row (StationCards.vue):
// mark, name and kind in the head, then the rows its source gives (lib/layers/card.ts). The
// label column is as wide as the widest possible label so that values stay still as rows come
// and go. It belongs to the map only: no Message, path, packets or Forget; it cannot be pinned
// or dragged.
import { computed } from "vue";
import IconButton from "@/components/IconButton.vue";
import LayerMark from "@/components/LayerMark.vue";
import type { OpenThing } from "@/composables/useLayerThings";
import { t } from "@/i18n";
import { cardLabels, cardRows, thingSub, thingTitle } from "@/lib/layers/card";
import { kindShape } from "@/lib/layers/traffic";

const props = defineProps<{ open: OpenThing; now: number }>();
const emit = defineEmits<{ close: [] }>();

const title = computed(() => thingTitle(props.open.layer, props.open.thing));
const rows = computed(() => cardRows(props.open.layer, props.open.thing, props.open.source, props.now));
const labels = computed(() => cardLabels(props.open.layer, props.open.thing, props.open.source));
</script>

<template>
  <section class="card layercard" :aria-label="thingSub(open.layer)" :data-thing="`${open.layer}:${open.thing.id}`">
    <header class="card-head">
      <span class="layercard-mark" :class="{ emergency: open.thing.emergency }"><LayerMark :name="kindShape(open.layer, open.thing)" /></span>
      <div class="card-title">
        <span class="card-call">
          <strong>{{ title }}</strong>
        </span>
        <span class="muted">{{ thingSub(open.layer) }}</span>
      </div>
      <IconButton kind="close" class="card-close" :label="t('iconbutton.close')" @click="emit('close')" />
    </header>
    <div class="card-body">
      <dl class="card-fields">
        <dt class="layercard-room" aria-hidden="true">
          <span v-for="label in labels" :key="label">{{ label }}</span>
        </dt>
        <dd class="layercard-room"></dd>
        <template v-for="row in rows" :key="row.label">
          <dt>{{ row.label }}</dt>
          <dd>{{ row.text }}</dd>
        </template>
      </dl>
    </div>
  </section>
</template>
