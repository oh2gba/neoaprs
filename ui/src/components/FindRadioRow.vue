<script setup lang="ts">
// The Find my radio button in the row of the radio's fields, in the Settings tab and the Radio
// step of the setup guide (composables/useFindRadio.ts runs the search). It is hidden where the
// daemon cannot look for the radio among the ports (`find` of the ports message) and shown until
// the daemon has said.
import { computed } from "vue";
import { t } from "@/i18n";
import { useDaemonContext } from "@/composables/useDaemonContext";

defineProps<{ id: string }>();
const { ports, findRadio } = useDaemonContext();
const available = computed(() => ports.value?.find ?? true);
</script>

<template>
  <div v-if="available" class="radiofind">
    <button :id="id" class="btn" type="button" :disabled="findRadio.running.value" @click="findRadio.start">
      {{ t("settings.find.button") }}
    </button>
  </div>
</template>
