<script setup lang="ts">
// The digipeaters the path builder (PathBuilder.vue) offers as the next hop (lib/pathbuilder.ts): for the first hop the ones we hear direct ("Digipeaters heard"), for a later one those seen next to the hop before it in the routes
// ("Next to OH2RDK-7"). A line a choice, a click adds it to the path: the call, how often it was seen (packets it repeated for us, or stations whose routes have it there; the hover title says which), when it was last heard direct
// and how far it is. The list has a height of its own, the same whatever it holds, and scrolls; "-" for none.
import { computed } from "vue";
import { t } from "@/i18n";
import { ageText, distanceText, NONE } from "@/lib/format";
import type { HopChoice } from "@/lib/pathbuilder";

const props = defineProps<{ choices: HopChoice[]; after: string | null; now: number }>();
const emit = defineEmits<{ pick: [call: string] }>();

const heading = computed(() => (props.after === null ? t("pathbuilder.heard") : t("pathbuilder.next_to", { call: props.after })));
const countTitle = (choice: HopChoice): string =>
  props.after === null ? t("nearby.repeated", { n: choice.count }) : t("pathbuilder.seen_next", { n: choice.count, call: props.after ?? "" });
const atTitle = (choice: HopChoice): string | undefined =>
  choice.at === null ? undefined : t("nearby.direct_last", { when: t("time.ago", { span: ageText(choice.at, props.now) }) });
</script>

<template>
  <section class="pathbuild-choices">
    <h3 class="pathbuild-heading">{{ heading }}</h3>
    <ul class="pathbuild-list" :aria-label="heading">
      <li v-for="choice in choices" :key="choice.call">
        <button type="button" class="pathbuild-choice" :title="t('pathbuilder.add_hop', { call: choice.call })" @click="emit('pick', choice.call)">
          <span class="mono pathbuild-call">{{ choice.call }}</span>
          <span class="pathbuild-num" :title="countTitle(choice)">{{ choice.count }}</span>
          <span class="pathbuild-num" :title="atTitle(choice)">{{ choice.at === null ? NONE : ageText(choice.at, now) }}</span>
          <span class="pathbuild-num">{{ choice.km === null ? NONE : t("stats.km", { km: distanceText(choice.km) }) }}</span>
        </button>
      </li>
      <li v-if="choices.length === 0" class="pathbuild-none muted">{{ NONE }}</li>
    </ul>
  </section>
</template>
