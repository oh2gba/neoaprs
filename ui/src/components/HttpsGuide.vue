<script setup lang="ts">
// The way to make a device trust NeoAPRS's certificate: the download, the fingerprint to compare with what the device shows, and the steps for the device this is (from its user agent; the choice can be changed), each
// short, in the systems' own words. Shown by the Settings tab's Web page group (SettingsHttps) and by the pop-up guide (PopupHelp) while the daemon serves https. The line at the end is the other way: open the secure page and
// continue past the browser's warning (not shown on the secure page itself, or where the caller has said the link is above).
import { computed, ref } from "vue";
import CopyField from "@/components/CopyField.vue";
import { CERT_FILE, CERT_PATH, DEVICES, STEPS, deviceOf, secureUrl, type Device } from "@/lib/httpshelp";
import type { HttpsState } from "@/protocol/protocol";

const props = withDefaults(defineProps<{ https: HttpsState; link?: boolean }>(), { link: true });

const device = ref<Device>(deviceOf(navigator.userAgent, navigator.maxTouchPoints));
const steps = computed(() => STEPS[device.value]);
const url = computed(() => secureUrl(props.https.port));
const onSecurePage = location.protocol === "https:";
</script>

<template>
  <section class="httpsguide" aria-label="Install the certificate">
    <div class="httpsguide-head">
      <a class="btn" :href="CERT_PATH" :download="CERT_FILE">Download certificate</a>
      <label for="https-device">for</label>
      <select id="https-device" v-model="device" class="input">
        <option v-for="d in DEVICES" :key="d.value" :value="d.value">{{ d.label }}</option>
      </select>
    </div>
    <div class="httpsguide-print">
      <span class="muted">Fingerprint</span>
      <CopyField :text="https.fingerprint" />
    </div>
    <ol class="popuphelp-steps">
      <li v-for="step in steps" :key="step">{{ step }}</li>
    </ol>
    <p v-if="link && !onSecurePage" class="popuphelp-plain">Or just <a :href="url">open the secure page</a> and continue past the warning.</p>
  </section>
</template>
