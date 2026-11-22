<script setup lang="ts">
// The browser's part of the Notifications group in Settings: Notify me, then Sound and
// Notification with Test buttons. The choice (lib/alertmode.ts) is kept in the browser, so each
// device decides. In the desktop app's own window the daemon alerts instead (lib/shell.ts
// `daemonTells`), so the box is hidden there (`alerts.daemonAlone`); on a Mac it is shown as "In
// this window" without the Notification row.
import { computed, ref, watch } from "vue";
import InfoTip from "@/components/InfoTip.vue";
import InstallApp from "@/components/InstallApp.vue";
import PopupHelp from "@/components/PopupHelp.vue";
import SettingsBox from "@/components/SettingsBox.vue";
import { t } from "@/i18n";
import type { BrowserAlerts } from "@/composables/useBrowserAlerts";
import { modeOf, wantsPopup, wantsSound, type AlertMode } from "@/lib/alertmode";
import type { HttpsState } from "@/protocol/protocol";

const props = defineProps<{ alerts: BrowserAlerts; https?: HttpsState | null; say?: (text: string) => void }>();
// Test answers go to the toast so that nothing moves.
watch([() => props.alerts.soundStatus.value, () => props.alerts.popupStatus.value], ([sound, popup], [soundBefore, popupBefore]) => {
  if (sound && sound !== soundBefore) props.say?.(sound);
  if (popup && popup !== popupBefore) props.say?.(popup);
});

const helpOpen = ref(false);

const on = computed(() => props.alerts.mode.value !== "off");
const sound = computed(() => wantsSound(props.alerts.mode.value));
const popup = computed(() => wantsPopup(props.alerts.mode.value));
/** The choice the Alert tickbox restores when ticked again: the last one that was on. */
const remembered = ref<AlertMode>(on.value ? props.alerts.mode.value : props.alerts.why.value === undefined ? "both" : "sound");
watch(
  () => props.alerts.mode.value,
  (mode) => {
    if (mode !== "off") remembered.value = mode;
  },
);

/** The permission is requested in the click handler; the tickboxes show the outcome. */
async function choose(next: AlertMode, event: Event): Promise<void> {
  await props.alerts.choose(next);
  if (event.target instanceof HTMLInputElement)
    event.target.checked = event.target.id === "alert-mode" ? on.value : event.target.id === "alert-sound" ? sound.value : popup.value;
}
const setAlert = (event: Event): Promise<void> => choose(on.value ? "off" : remembered.value, event);
const setSound = (event: Event): Promise<void> => choose(modeOf(!sound.value, popup.value), event);
const setPopup = (event: Event): Promise<void> => choose(modeOf(sound.value, !popup.value), event);
</script>

<template>
  <template v-if="!alerts.daemonAlone">
    <SettingsBox :title="t(alerts.app ? 'settings.browser.heading_app' : 'settings.browser.heading')">
      <div class="field">
        <label for="alert-mode">{{ t("settings.browser.mode") }}</label>
        <div class="field-control">
          <input id="alert-mode" class="check" type="checkbox" :checked="on" @change="setAlert" />
          <InfoTip :label="t('settings.about', { label: t('settings.browser.mode') })" picture="notifications">
            <span class="info-line">{{ t(alerts.app ? "settings.browser.mode_tip_app" : "settings.browser.mode_tip") }}</span>
          </InfoTip>
          <span v-if="alerts.note.value" class="muted" role="status">{{ alerts.note.value }}</span>
        </div>
      </div>
      <template v-if="on">
        <div class="field">
          <label for="alert-sound">{{ t("settings.browser.sound") }}</label>
          <div class="field-control">
            <input id="alert-sound" class="check" type="checkbox" :checked="sound" :disabled="sound && !popup" @change="setSound" />
            <button id="alert-test-sound" class="btn" type="button" @click="alerts.testSound">{{ t("settings.browser.test_sound") }}</button>
          </div>
        </div>
        <div v-if="!alerts.app" class="field">
          <label for="alert-popup">{{ t("settings.browser.popup") }}</label>
          <div class="field-control">
            <input
              id="alert-popup"
              class="check"
              type="checkbox"
              :checked="popup"
              :disabled="(popup && !sound) || (!popup && alerts.why.value !== undefined)"
              :title="alerts.why.value"
              @change="setPopup"
            />
            <button id="alert-test-popup" class="btn" type="button" @click="alerts.testPopup">{{ t("settings.browser.test_popup") }}</button>
            <button v-if="!alerts.secure" id="alert-enable-popups" class="linkbtn" type="button" :aria-expanded="helpOpen" @click="helpOpen = !helpOpen">
              {{ t("settings.browser.enable_popups") }}
            </button>
          </div>
        </div>
      </template>
      <InstallApp v-if="!alerts.app" />
    </SettingsBox>
    <PopupHelp v-if="!alerts.secure && helpOpen" :https="https" @close="helpOpen = false" />
  </template>
</template>
