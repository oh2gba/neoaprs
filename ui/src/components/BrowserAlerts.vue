<script setup lang="ts">
// The browser's part of the Settings tab's "Notifications" group, a box of its own inside the group ("In this browser", components/SettingsBox.vue), laid out as the box "On the NeoAPRS computer" is: an **Alert** tickbox first, and while it is ticked two tickboxes, **Sound** and **Pop-up**, each with its Test button
// beside it (and "Enable pop-ups…" beside Pop-up where the page is not a secure context). What is kept is the one choice of lib/alertmode.ts (off, sound, sound and pop-up, pop-up only), in the browser and not on the daemon, so each device decides; Alert ticked with neither kind is the sound. The pop-up is disabled, with the reason as its title, where the browser
// cannot show one. The answers of the Test buttons are said (`say`) in the page's toast. "Enable pop-ups…" opens the steps for the person's browser (PopupHelp), which start with the secure page while the daemon serves https (`https`).
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
// the answers of the two Test buttons are said in the toast, so that nothing moves
watch([() => props.alerts.soundStatus.value, () => props.alerts.popupStatus.value], ([sound, popup], [soundBefore, popupBefore]) => {
  if (sound && sound !== soundBefore) props.say?.(sound);
  if (popup && popup !== popupBefore) props.say?.(popup);
});

const helpOpen = ref(false);

const on = computed(() => props.alerts.mode.value !== "off");
const sound = computed(() => wantsSound(props.alerts.mode.value));
const popup = computed(() => wantsPopup(props.alerts.mode.value));
/** What the Alert tickbox goes back to when it is ticked again: the last choice that was on. */
const remembered = ref<AlertMode>(on.value ? props.alerts.mode.value : props.alerts.why.value === undefined ? "both" : "sound");
watch(
  () => props.alerts.mode.value,
  (mode) => {
    if (mode !== "off") remembered.value = mode;
  },
);

/** The permission is asked here, in the click; the tickboxes show what came of it. */
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
  <SettingsBox :title="t('settings.browser.heading')">
    <div class="field">
      <label for="alert-mode">{{ t("settings.browser.mode") }}</label>
      <div class="field-control">
        <input id="alert-mode" class="check" type="checkbox" :checked="on" @change="setAlert" />
        <InfoTip :label="t('settings.about', { label: t('settings.browser.mode') })" picture="notifications">
          <span class="info-line">{{ t("settings.browser.mode_tip") }}</span>
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
      <div class="field">
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
    <InstallApp />
  </SettingsBox>
  <PopupHelp v-if="!alerts.secure && helpOpen" :https="https" @close="helpOpen = false" />
</template>
