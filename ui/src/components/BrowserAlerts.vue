<script setup lang="ts">
// The browser's part of the Settings tab's "Notifications" group, a box of its own inside the group ("In this browser", components/SettingsBox.vue): what this browser does for a new message (off, sound, sound and pop-up, pop-up only), with a Test button for the sound and one for the pop-up, each shown only while the choice has that part (none while it is off) and each with
// the few words of what happened, said (`say`) in the page's toast. The choice is kept in the browser, not on the daemon, so each device decides. The options with a pop-up are disabled, with the reason as their title, where the browser cannot show one; where the
// page is not a secure context (plain http from another computer) "Enable pop-ups…" opens the steps for the person's browser (PopupHelp), which start with the secure page while the daemon serves https (`https`).
import { ref, watch } from "vue";
import InstallApp from "@/components/InstallApp.vue";
import PopupHelp from "@/components/PopupHelp.vue";
import SettingsBox from "@/components/SettingsBox.vue";
import { t } from "@/i18n";
import type { BrowserAlerts } from "@/composables/useBrowserAlerts";
import { MODES, wantsPopup, wantsSound, type AlertMode } from "@/lib/alertmode";
import type { HttpsState } from "@/protocol/protocol";

const props = defineProps<{ alerts: BrowserAlerts; https?: HttpsState | null; say?: (text: string) => void }>();
// the answers of the two Test buttons are said in the toast, so that nothing moves
watch([() => props.alerts.soundStatus.value, () => props.alerts.popupStatus.value], ([sound, popup], [soundBefore, popupBefore]) => {
  if (sound && sound !== soundBefore) props.say?.(sound);
  if (popup && popup !== popupBefore) props.say?.(popup);
});

const helpOpen = ref(false);

/** The permission is asked here, in the click; the select shows what came of it. */
async function onChoose(event: Event): Promise<void> {
  const select = event.target;
  if (!(select instanceof HTMLSelectElement)) return;
  await props.alerts.choose(select.value as AlertMode);
  select.value = props.alerts.mode.value;
}
</script>

<template>
  <SettingsBox :title="t('settings.browser.heading')">
    <div class="field">
      <label for="alert-mode">{{ t("settings.browser.mode") }}</label>
      <div class="field-control">
        <select id="alert-mode" class="input" :value="alerts.mode.value" :title="alerts.why.value" @change="onChoose">
          <option
            v-for="mode in MODES"
            :key="mode.value"
            :value="mode.value"
            :disabled="wantsPopup(mode.value) && alerts.why.value !== undefined"
            :title="wantsPopup(mode.value) ? alerts.why.value : undefined"
          >
            {{ mode.label }}
          </option>
        </select>
        <span v-if="alerts.note.value" class="muted" role="status">{{ alerts.note.value }}</span>
        <button v-if="!alerts.secure" id="alert-enable-popups" class="linkbtn" type="button" :aria-expanded="helpOpen" @click="helpOpen = !helpOpen">
          {{ t("settings.browser.enable_popups") }}
        </button>
      </div>
    </div>
    <div v-if="wantsSound(alerts.mode.value)" class="field">
      <label for="alert-test-sound">{{ t("settings.browser.sound") }}</label>
      <div class="field-control">
        <button id="alert-test-sound" class="btn" type="button" @click="alerts.testSound">{{ t("settings.browser.test_sound") }}</button>
      </div>
    </div>
    <div v-if="wantsPopup(alerts.mode.value)" class="field">
      <label for="alert-test-popup">{{ t("settings.browser.popup") }}</label>
      <div class="field-control">
        <button id="alert-test-popup" class="btn" type="button" @click="alerts.testPopup">{{ t("settings.browser.test_popup") }}</button>
        <button v-if="!alerts.secure && alerts.popupStatus.value" class="linkbtn" type="button" @click="helpOpen = true">
          {{ t("settings.browser.enable_popups") }}
        </button>
      </div>
    </div>
    <InstallApp />
  </SettingsBox>
  <PopupHelp v-if="!alerts.secure && helpOpen" :https="https" @close="helpOpen = false" />
</template>
