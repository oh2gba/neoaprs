<script setup lang="ts">
// The Find my radio button, in the row of the radio's fields where the Settings tab and the Radio step of the setup guide both have it (composables/useFindRadio.ts runs the search and puts what it finds in the settings, or in the guide's answers).
// It is not there where the daemon cannot look for the radio among the ports (`find` of the ports message: Linux, Windows and macOS can); it is shown until the daemon has said.
import { computed } from "vue";
import { t } from "@/i18n";
import { useDaemonContext } from "@/composables/useDaemonContext";

defineProps<{ id: string }>();
const { ports, findRadio } = useDaemonContext();
const available = computed(() => ports.value?.find ?? true);
</script>

<template>
  <div v-if="available" class="radiofind">
    <button :id="id" class="btn" type="button" :disabled="findRadio.running.value" @click="findRadio.start">{{ t("settings.find.button") }}</button>
  </div>
</template>
