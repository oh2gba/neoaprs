<script setup lang="ts">
// One row of the HF tests tab, the same on the board and among the past tests: the time in UTC (the
// viewer's own in the title) with how long until it on the board, the dial and the calls, and the note
// on one line with the whole text in the title. The column on the right is the board's Delete or Join
// (the slot); it keeps its width, empty among the past tests.
import TagMark from "@/components/TagMark.vue";
import { t } from "@/i18n";
import { inText, localText, noteOf, whenText, type SkedGroup } from "@/lib/skeds";

defineProps<{ group: SkedGroup; now?: number }>();
</script>

<template>
  <li class="sked" :class="{ mine: group.ours.length > 0 }">
    <div class="sked-main">
      <p class="sked-when" :title="localText(group.from, group.to)">
        <strong>{{ whenText(group.from, group.to) }}</strong>
        <template v-if="now !== undefined">
          {{ " " }}<span class="muted">{{ inText(group.from, now) }}</span>
        </template>
      </p>
      <p class="sked-line">
        <span class="mono sked-dial">{{ group.dial }}</span>
        <span v-for="r in group.rows" :key="r.id" class="sked-call">
          <strong class="mono">{{ r.call }}</strong>
          <TagMark v-if="r.ours" tone="outline">{{ t("skeds.ours") }}</TagMark>
        </span>
      </p>
      <p v-if="noteOf(group) !== ''" class="sked-note muted" :title="noteOf(group)">{{ noteOf(group) }}</p>
    </div>
    <div class="sked-actions">
      <slot />
    </div>
  </li>
</template>
