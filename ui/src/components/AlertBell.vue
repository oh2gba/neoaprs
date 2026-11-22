<script setup lang="ts">
// A quiet bell for a station that has an alert set (lib/stationalert.ts), beside the call in the
// Stations table and on the station's card. The table always keeps the slot, empty without an
// alert, so that setting one moves nothing.
import { computed } from "vue";
import { t } from "@/i18n";
import { alertSummary } from "@/lib/stationalert";
import type { AlertWhen } from "@/protocol/protocol";

const props = defineProps<{ alert: AlertWhen | null | undefined }>();
const title = computed(() => (props.alert ? t("station.alert.bell", { what: alertSummary(props.alert) }) : undefined));
</script>

<template>
  <span class="alert-bell" :title="title">
    <svg
      v-if="alert"
      role="img"
      :aria-label="title"
      width="12"
      height="12"
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      stroke-width="1.5"
      stroke-linecap="round"
      stroke-linejoin="round"
    >
      <path d="M4 11.5V7a4 4 0 0 1 8 0v4.5l1.5 1.5h-11zM6.5 13.5a1.5 1.5 0 0 0 3 0" />
    </svg>
  </span>
</template>
