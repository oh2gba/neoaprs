<script setup lang="ts">
// The toast while Find my radio runs (composables/useFindRadio.ts): which port it is trying and how far it is, and Cancel. It goes when the search ends; what the end says is another toast (the Undo of the settings it changed, a notice, or
// the daemon's error). It is in the colours of the notice.
import { t } from "@/i18n";
import type { FindRadio } from "@/composables/useFindRadio";

defineProps<{ find: Pick<FindRadio, "running" | "text" | "cancel"> }>();
</script>

<template>
  <div v-if="find.running.value" class="toast notice findradio" role="status">
    <span>{{ find.text.value }}</span>
    <button class="linkbutton findradio-cancel" type="button" @click="find.cancel()">{{ t("settings.find.cancel") }}</button>
  </div>
</template>
