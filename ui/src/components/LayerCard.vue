<script setup lang="ts">
// The card of an aircraft or a ship on the map, one more card of the station cards' row (components/StationCards.vue), in their frame, head and cross: its mark, what it is called and what kind of thing it is in the
// head, then what its source says of it, a row only where it has something (lib/layers/card.ts), and the source's name last. It is the map's alone: nothing of a station (no Message, no path, no packets, no Forget),
// it cannot be pinned or dragged, and it closes with its cross (and as the page closes it: components/StationCards.vue, composables/useLayerThings.ts).
import { computed } from "vue";
import IconButton from "@/components/IconButton.vue";
import LayerMark from "@/components/LayerMark.vue";
import type { OpenThing } from "@/composables/useLayerThings";
import { t } from "@/i18n";
import { cardRows, thingSub, thingTitle } from "@/lib/layers/card";
import { thingShape } from "@/lib/layers/traffic";

const props = defineProps<{ open: OpenThing; now: number }>();
const emit = defineEmits<{ close: [] }>();

const title = computed(() => thingTitle(props.open.layer, props.open.thing));
const rows = computed(() => cardRows(props.open.layer, props.open.thing, props.open.source, props.now));
</script>

<template>
  <section class="card layercard" :aria-label="thingSub(open.layer)" :data-thing="`${open.layer}:${open.thing.id}`">
    <header class="card-head">
      <span class="layercard-mark" :class="{ emergency: open.thing.emergency }"><LayerMark :name="thingShape(open.layer, open.thing)" /></span>
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
        <template v-for="row in rows" :key="row.label">
          <dt>{{ row.label }}</dt>
          <dd>{{ row.text }}</dd>
        </template>
      </dl>
    </div>
  </section>
</template>
