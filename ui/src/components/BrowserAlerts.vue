<script setup lang="ts">
// The browser's part of the Settings tab's "Notifications" group: what this browser does for a new message (off, sound, sound and pop-up, pop-up only), with a Test button for the sound and one for the pop-up, each with
// the few words of what happened. The choice is kept in the browser, not on the daemon, so each device decides. The options with a pop-up are disabled, with the reason as their title, where the browser cannot show one.
import type { BrowserAlerts } from "@/composables/useBrowserAlerts";
import { MODES, wantsPopup, type AlertMode } from "@/lib/alertmode";

const props = defineProps<{ alerts: BrowserAlerts }>();

/** The permission is asked here, in the click; the select shows what came of it. */
async function onChoose(event: Event): Promise<void> {
  const select = event.target;
  if (!(select instanceof HTMLSelectElement)) return;
  await props.alerts.choose(select.value as AlertMode);
  select.value = props.alerts.mode.value;
}
</script>

<template>
  <h3 class="subgroup">In this browser</h3>
  <div class="field">
    <label for="alert-mode">Alert for a new message</label>
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
    </div>
  </div>
  <div class="field">
    <label for="alert-test-sound">Sound</label>
    <div class="field-control">
      <button id="alert-test-sound" class="btn" type="button" @click="alerts.testSound">Test sound</button>
      <span v-if="alerts.soundStatus.value" class="muted" role="status">{{ alerts.soundStatus.value }}</span>
    </div>
  </div>
  <div class="field">
    <label for="alert-test-popup">Pop-up</label>
    <div class="field-control">
      <button id="alert-test-popup" class="btn" type="button" @click="alerts.testPopup">Test pop-up</button>
      <span v-if="alerts.popupStatus.value" class="muted" role="status">{{ alerts.popupStatus.value }}</span>
    </div>
  </div>
</template>
