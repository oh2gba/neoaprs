<script setup lang="ts">
// What the Settings tab's Web page group adds under the switch for the secure connection: why it is not working when it was asked for and could not start (the daemon's reason, in the page's words), and, while it is, a
// heading that opens the guide to install the certificate on a device (HttpsGuide).
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
