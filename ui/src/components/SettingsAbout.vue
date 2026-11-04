<script setup lang="ts">
// The About group, after Help, the last of the Settings tab: what NeoAPRS is and which version this is (the daemon's), who made it and when, the licence and the source as plain links, the HF modem with its
// version, a thanks to everyone, and as the quiet last line Download logs, which saves the support file (Help's Send feedback / logs is the way to reach the project). Text and links only; no control. A call in running text stays in the body font (the monospace font has another height, and a selection of it looks cut).
import { computed } from "vue";
import { t } from "@/i18n";
import SettingsGroup from "@/components/SettingsGroup.vue";
import RichMessage from "@/components/RichMessage.vue";
import { useDaemonContext } from "@/composables/useDaemonContext";
import { useSupportLogs } from "@/composables/useSupportLogs";
import { ABOUT_AUTHOR, ABOUT_ISSUES_URL, ABOUT_LICENSE_URL, ABOUT_MODEM, ABOUT_MODEM_URL, ABOUT_SOURCE_URL, ABOUT_YEAR } from "@/lib/about";
import { SUPPORT_ADDRESS } from "@/lib/support";
import { LIMITS } from "@/protocol/lists";

const { version, call, connection, panel } = useDaemonContext();
const logs = useSupportLogs({ call, connection, daemonVersion: version, panelWidth: panel.width });
const downloadLabel = computed(() => (logs.running.value ? t("settings.help.collecting") : t("settings.help.download")));
</script>

<template>
  <SettingsGroup id="about" class="about" :title="t('settings.about.group')">
    <p>
      <RichMessage id="settings.about.intro" :params="{ version: version, year: ABOUT_YEAR }"
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
    <p>
      <RichMessage id="settings.about.modem"
        ><template #modem
          ><a :href="ABOUT_MODEM_URL" target="_blank" rel="noopener noreferrer">{{ ABOUT_MODEM }} {{ LIMITS.mercury.version }}</a></template
        ></RichMessage
      >
    </p>
    <p class="muted">{{ t("settings.about.thanks") }}</p>
    <p>
      <RichMessage id="settings.about.feedback"
        ><template #issues
          ><a :href="ABOUT_ISSUES_URL" target="_blank" rel="noopener noreferrer">{{ t("settings.about.issues") }}</a></template
        ><template #mail
          ><a :href="`mailto:${SUPPORT_ADDRESS}`">{{ SUPPORT_ADDRESS }}</a></template
        ></RichMessage
      >
    </p>
    <p class="about-download muted">
      <button id="set-help-logs" type="button" class="linkbtn" :disabled="logs.running.value" @click="logs.collect">{{ downloadLabel }}</button>
      <span role="status"
        ><template v-if="logs.saved.value !== null"> · {{ t("settings.help.saved", { file: logs.saved.value }) }}</template
        ><template v-else-if="logs.problem.value">
          · <span class="field-error">{{ logs.problem.value }}</span></template
        ></span
      >
    </p>
  </SettingsGroup>
</template>
