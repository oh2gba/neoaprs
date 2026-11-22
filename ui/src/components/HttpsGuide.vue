<script setup lang="ts">
// How to make a device trust NeoAPRS's certificate: the download, the fingerprint to compare and
// the steps for this device (from its user agent), in the systems' own words. Shown in Settings
// (SettingsHttps) and in the notification guide (PopupHelp) while the daemon serves https. The
// last line offers the other way: open the secure page and continue past the warning.
import { computed, ref } from "vue";
import CopyField from "@/components/CopyField.vue";
import RichMessage from "@/components/RichMessage.vue";
import { t } from "@/i18n";
import { CERT_FILE, CERT_PATH, DEVICES, STEPS, deviceOf, secureUrl, type Device } from "@/lib/httpshelp";
import type { HttpsState } from "@/protocol/protocol";

const props = withDefaults(defineProps<{ https: HttpsState; link?: boolean }>(), { link: true });

const device = ref<Device>(deviceOf(navigator.userAgent, navigator.maxTouchPoints));
const steps = computed(() => STEPS[device.value]);
const url = computed(() => secureUrl(props.https.port));
const onSecurePage = location.protocol === "https:";
</script>

<template>
  <section class="httpsguide" :aria-label="t('help.https.label')">
    <div class="httpsguide-head">
      <a class="btn" :href="CERT_PATH" :download="CERT_FILE">{{ t("help.https.download") }}</a>
      <label for="https-device">{{ t("help.https.for_device") }}</label>
      <select id="https-device" v-model="device" class="input">
        <option v-for="d in DEVICES" :key="d.value" :value="d.value">{{ d.label }}</option>
      </select>
    </div>
    <div class="httpsguide-print">
      <span class="muted">{{ t("help.https.fingerprint") }}</span>
      <CopyField :text="https.fingerprint" />
    </div>
    <ol class="popuphelp-steps">
      <li v-for="step in steps" :key="step">{{ step }}</li>
    </ol>
    <p v-if="link && !onSecurePage" class="popuphelp-plain">
      <RichMessage id="help.https.or_just"
        ><template #link
          ><a :href="url">{{ t("help.https.open_secure") }}</a></template
        ></RichMessage
      >
    </p>
  </section>
</template>
