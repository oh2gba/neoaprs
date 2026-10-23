<script setup lang="ts">
// What a click on a packet of the log opens: the packet in a few plain facts (who sent it, what kind it is, what it says, how it reached us or which path we sent it by, when; lib/packetview.ts), and under "Raw", closed, the packet as the parser decoded it, as JSON.
import { computed } from "vue";
import DisclosureBox from "@/components/DisclosureBox.vue";
import RouteText from "@/components/RouteText.vue";
import { decodedJson } from "@/lib/packets";
import { packetFacts } from "@/lib/packetview";
import type { PacketRow } from "@/protocol/protocol";

const props = defineProps<{ row: PacketRow }>();
const facts = computed(() => packetFacts(props.row));
</script>

<template>
  <div class="packet-detail">
    <dl class="card-fields">
      <template v-for="fact in facts" :key="fact.label">
        <dt>{{ fact.label }}</dt>
        <dd>
          <RouteText v-if="fact.route" :text="fact.text" /><template v-else>{{ fact.text }}</template>
        </dd>
      </template>
    </dl>
    <DisclosureBox plain class="more" title="Raw">
      <pre class="json">{{ decodedJson(row) }}</pre>
    </DisclosureBox>
  </div>
</template>
