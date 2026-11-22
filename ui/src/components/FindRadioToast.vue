<script setup lang="ts">
// The toast shown while Find my radio runs (composables/useFindRadio.ts): the port being tried,
// the progress and Cancel. It goes when the search ends; the outcome is a separate toast. It
// uses the notice colours.
import { t } from "@/i18n";
import type { FindRadio } from "@/composables/useFindRadio";

defineProps<{ find: Pick<FindRadio, "running" | "text" | "cancel"> }>();
</script>

<template>
  <div v-if="find.running.value" class="toast notice findradio" role="status">
    <span>{{ find.text.value }}</span>
    <button class="linkbutton findradio-cancel" type="button" @click="find.cancel()">
      {{ t("settings.find.cancel") }}
    </button>
  </div>
</template>
