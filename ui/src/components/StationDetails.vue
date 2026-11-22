<script setup lang="ts">
// The rest of a station's card, folded until "Details" is opened: how its packets reach us, when it
// was first heard, packet counts, and what the daemon decodes beyond the position (storm data,
// signpost text, Maidenhead locator, telemetry). Rows with nothing to say are left out.
import { computed } from "vue";
import DisclosureBox from "@/components/DisclosureBox.vue";
import { t } from "@/i18n";
import { locatorText, stormText, telemetryBitsText, telemetryText } from "@/lib/details";
import { dateTimeText, pathText } from "@/lib/format";
import { bestText, heardText } from "@/lib/routes";
import type { StationRow } from "@/protocol/protocol";

const props = defineProps<{ row: StationRow }>();

const heard = computed(() => heardText(props.row));
const best = computed(() => bestText(props.row));
/**
 * "312" for our own station and objects, which are not heard; "312 · 14 in the last hour"
 * otherwise.
 */
const packets = computed(() =>
  props.row.is_me || props.row.own ? String(props.row.packets) : t("station.packets_value", { total: props.row.packets, hour: props.row.packets_hour }),
);
</script>

<template>
  <DisclosureBox plain class="more card-details" :title="t('station.card.details')">
    <dl class="card-fields">
      <template v-if="row.storm !== null">
        <dt>{{ t("station.field.storm") }}</dt>
        <dd>{{ stormText(row.storm) }}</dd>
      </template>
      <template v-if="row.sign !== null">
        <dt>{{ t("station.field.sign") }}</dt>
        <dd>{{ row.sign }}</dd>
      </template>
      <template v-if="row.locator !== null">
        <dt>{{ t("station.field.locator") }}</dt>
        <dd>{{ locatorText(row.locator) }}</dd>
      </template>
      <template v-if="row.telemetry !== null">
        <dt>{{ t("station.field.telemetry") }}</dt>
        <dd :title="dateTimeText(row.telemetry_at)">{{ telemetryText(row.telemetry) }}</dd>
        <dt>{{ t("station.field.bits") }}</dt>
        <dd>{{ telemetryBitsText(row.telemetry) }}</dd>
      </template>
      <dt>{{ t("station.field.first_heard") }}</dt>
      <dd>{{ dateTimeText(row.first_heard) }}</dd>
      <template v-if="row.last_path.length > 0">
        <dt>{{ t("station.field.path") }}</dt>
        <dd class="mono">{{ pathText(row.last_path) }}</dd>
      </template>
      <template v-if="heard !== '-'">
        <dt>{{ t("station.field.heard") }}</dt>
        <dd>{{ heard }}</dd>
      </template>
      <template v-if="best !== '-'">
        <dt>{{ t("station.field.best_route") }}</dt>
        <dd>{{ best }}</dd>
      </template>
      <dt>{{ t("station.field.packets") }}</dt>
      <dd>{{ packets }}</dd>
    </dl>
  </DisclosureBox>
</template>
