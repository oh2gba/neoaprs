<script setup lang="ts">
// The About group, after Help, the last of the Settings tab: what NeoAPRS is and which version this is (the daemon's, as the footer says it), who made it, the licence and the source as plain links, and a thanks. Text and links only; no control.
import { t } from "@/i18n";
import RichMessage from "@/components/RichMessage.vue";
import { useDaemonContext } from "@/composables/useDaemonContext";
import { ABOUT_AUTHOR, ABOUT_LICENSE_URL, ABOUT_SOURCE_URL, ABOUT_THANKS } from "@/lib/about";

const { version } = useDaemonContext();
const [first, second, third] = ABOUT_THANKS;
</script>

<template>
  <fieldset class="about">
    <legend>{{ t("settings.about.group") }}</legend>
    <p>
      <RichMessage id="settings.about.intro" :params="{ version: version }"
        ><template #call
          ><span class="mono">{{ ABOUT_AUTHOR }}</span></template
        ></RichMessage
      >
    </p>
    <p>
      <RichMessage id="settings.about.license"
        ><template #license
          ><a :href="ABOUT_LICENSE_URL" target="_blank" rel="noopener noreferrer">{{ t("settings.about.license_link") }}</a></template
        ></RichMessage
      >
    </p>
    <p>
      <a :href="ABOUT_SOURCE_URL" target="_blank" rel="noopener noreferrer">{{ t("settings.about.source") }}</a>
    </p>
    <p class="muted">
      <RichMessage id="settings.about.thanks"
        ><template #first
          ><span class="mono">{{ first }}</span></template
        ><template #second
          ><span class="mono">{{ second }}</span></template
        ><template #third
          ><span class="mono">{{ third }}</span></template
        ></RichMessage
      >
    </p>
  </fieldset>
</template>
