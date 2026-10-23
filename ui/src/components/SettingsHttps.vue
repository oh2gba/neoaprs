<script setup lang="ts">
// What the Settings tab's Web page group adds under the switch for the secure connection: why it is not working when it was asked for and could not start, and, while it is, a link that opens the guide to install the
// certificate on this device (HttpsGuide).
import { ref } from "vue";
import HttpsGuide from "@/components/HttpsGuide.vue";
import type { HttpsState } from "@/protocol/protocol";

defineProps<{ https: HttpsState }>();

const open = ref(false);
</script>

<template>
  <p v-if="https.problem" class="field-error" role="alert">{{ https.problem }}</p>
  <div v-if="https.on" class="field">
    <label for="set-web-cert">Certificate</label>
    <div class="field-control">
      <button id="set-web-cert" class="linkbtn" type="button" :aria-expanded="open" @click="open = !open">Install on a device…</button>
    </div>
  </div>
  <HttpsGuide v-if="https.on && open" :https="https" />
</template>
