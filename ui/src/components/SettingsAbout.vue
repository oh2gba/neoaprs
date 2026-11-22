<script setup lang="ts">
// The About group, last of the Settings tab: the version, authors, licence, source links, the HF
// modem and (where installed) the sound card modem with versions, and Download logs as the last
// line.
import { computed } from "vue";
import { t } from "@/i18n";
import SettingsGroup from "@/components/SettingsGroup.vue";
import RichMessage from "@/components/RichMessage.vue";
import { useDaemonContext } from "@/composables/useDaemonContext";
import { useSupportLogs } from "@/composables/useSupportLogs";
import {
  ABOUT_AUTHOR,
  ABOUT_DIREWOLF,
  ABOUT_DIREWOLF_URL,
  ABOUT_LICENSE_URL,
  ABOUT_MODEM,
  ABOUT_MODEM_URL,
  ABOUT_SOURCE_URL,
  ABOUT_YEAR,
} from "@/lib/about";
import { LIMITS } from "@/protocol/lists";

const { version, call, connection, panel, status } = useDaemonContext();
const logs = useSupportLogs({ call, connection, daemonVersion: version, panelWidth: panel.width });
/** Whether this installation carries Direwolf, known from the status. */
const direwolf = computed(() => status.value !== null && !status.value.unavailable_types.includes("direwolf"));
const downloadLabel = computed(() =>
  logs.running.value ? t("settings.help.collecting") : t("settings.help.download"),
);
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
          ><a :href="ABOUT_LICENSE_URL" target="_blank" rel="noopener noreferrer">{{
            t("settings.about.license_link")
          }}</a></template
        ></RichMessage
      >
    </p>
    <p>
      <a :href="ABOUT_SOURCE_URL" target="_blank" rel="noopener noreferrer">{{ t("settings.about.source") }}</a>
    </p>
    <p>
      <RichMessage id="settings.about.modem"
        ><template #modem
          ><a :href="ABOUT_MODEM_URL" target="_blank" rel="noopener noreferrer"
            >{{ ABOUT_MODEM }} {{ LIMITS.mercury.version }}</a
          ></template
        ></RichMessage
      >
    </p>
    <p v-if="direwolf">
      <RichMessage id="settings.about.direwolf"
        ><template #modem
          ><a :href="ABOUT_DIREWOLF_URL" target="_blank" rel="noopener noreferrer"
            >{{ ABOUT_DIREWOLF }} {{ LIMITS.soundCard.version }}</a
          ></template
        ></RichMessage
      >
    </p>
    <p class="muted">{{ t("settings.about.thanks") }}</p>
    <p>
      {{ t("settings.about.feedback", { button: t("settings.help.send") }) }}
    </p>
    <p class="about-download muted">
      <button id="set-help-logs" type="button" class="linkbtn" :disabled="logs.running.value" @click="logs.collect">
        {{ downloadLabel }}
      </button>
      <span role="status"
        ><template v-if="logs.saved.value !== null">
          · {{ t("settings.help.saved", { file: logs.saved.value }) }}</template
        ><template v-else-if="logs.problem.value">
          · <span class="field-error">{{ logs.problem.value }}</span></template
        ></span
      >
    </p>
  </SettingsGroup>
</template>
