<script setup lang="ts">
// The Web page group's addition under the secure connection switch: the daemon's reason when https
// was asked for and could not start, and a heading with the guide to install the certificate
// (HttpsGuide).
import DisclosureBox from "@/components/DisclosureBox.vue";
import HttpsGuide from "@/components/HttpsGuide.vue";
import { t } from "@/i18n";
import { reasonText } from "@/lib/httpshelp";
import type { HttpsState } from "@/protocol/protocol";

defineProps<{ https: HttpsState }>();
</script>

<template>
  <p v-if="https.reason" class="field-error" role="alert">{{ reasonText(https.reason) }}</p>
  <DisclosureBox v-if="https.on" :title="t('help.https.install_title')"><HttpsGuide :https="https" /></DisclosureBox>
</template>
