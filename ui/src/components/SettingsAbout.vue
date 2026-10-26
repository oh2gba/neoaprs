<script setup lang="ts">
// The About group, after Help, the last of the Settings tab: what NeoAPRS is and which version this is (the daemon's), who made it, the licence and the source as plain links, and a thanks. Text and links only; no control. A call in running text stays in the body font (the monospace font has another height, and a selection of it looks cut).
import { t } from "@/i18n";
import RichMessage from "@/components/RichMessage.vue";
import { useDaemonContext } from "@/composables/useDaemonContext";
import { ABOUT_AUTHOR, ABOUT_ISSUES_URL, ABOUT_LICENSE_URL, ABOUT_SOURCE_URL, ABOUT_THANKS } from "@/lib/about";
import { SUPPORT_ADDRESS } from "@/lib/support";

const { version } = useDaemonContext();
const [first, second, third] = ABOUT_THANKS;
</script>

<template>
  <fieldset class="about">
    <legend>{{ t("settings.about.group") }}</legend>
    <p>
      <RichMessage id="settings.about.intro" :params="{ version: version }"
        ><template #call>{{ ABOUT_AUTHOR }}</template></RichMessage
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
        ><template #first>{{ first }}</template
        ><template #second>{{ second }}</template
        ><template #third>{{ third }}</template></RichMessage
      >
    </p>
    <p>
      <RichMessage id="settings.about.feedback"
        ><template #issues
          ><a :href="ABOUT_ISSUES_URL" target="_blank" rel="noopener noreferrer">{{ t("settings.about.issues") }}</a></template
        ><template #mail
          ><a :href="`mailto:${SUPPORT_ADDRESS}`">{{ SUPPORT_ADDRESS }}</a></template
        ></RichMessage
      >
    </p>
  </fieldset>
</template>
