<script setup lang="ts">
// The Settings tab's group for this browser: whether the page alerts for a message to us (a notification, else a chime and the alert of the browser tab), with Sound and Notifications, and a Test button. They are kept in the
// browser, not on the daemon, so each device decides. Notifications is disabled, with the reason as its title, where the browser cannot show them.
import type { BrowserAlerts } from "@/composables/useBrowserAlerts";

const props = defineProps<{ alerts: BrowserAlerts }>();

function onFlag(flag: { value: boolean }, event: Event): void {
  if (event.target instanceof HTMLSelectElement) flag.value = event.target.value === "true";
}
/** The permission is asked here, in the click; the switch shows what came of it. */
async function onNotify(event: Event): Promise<void> {
  const select = event.target;
  if (!(select instanceof HTMLSelectElement)) return;
  await props.alerts.setNotify(select.value === "true");
  select.value = String(props.alerts.notifyOn.value);
}
</script>

<template>
  <fieldset class="browser-alerts">
    <legend>This browser</legend>
    <div class="field">
      <label for="alert-web">Web alert</label>
      <div class="field-control">
        <select id="alert-web" class="input" :value="String(alerts.enabled.value)" @change="onFlag(alerts.enabled, $event)">
          <option value="true">yes</option>
          <option value="false">no</option>
        </select>
        <button
          id="alert-test"
          class="btn"
          type="button"
          :disabled="!alerts.enabled.value"
          :title="alerts.enabled.value ? undefined : 'Switch the web alert on'"
          @click="alerts.test"
        >
          Test
        </button>
      </div>
    </div>
    <div class="field">
      <label for="alert-sound">Sound</label>
      <div class="field-control">
        <select id="alert-sound" class="input" :disabled="!alerts.enabled.value" :value="String(alerts.sound.value)" @change="onFlag(alerts.sound, $event)">
          <option value="true">yes</option>
          <option value="false">no</option>
        </select>
      </div>
    </div>
    <div class="field" :title="alerts.notifyTitle.value">
      <label for="alert-notify">Notifications</label>
      <div class="field-control">
        <select
          id="alert-notify"
          class="input"
          :disabled="!alerts.enabled.value || alerts.notifyTitle.value !== undefined"
          :value="String(alerts.notifyOn.value)"
          @change="onNotify"
        >
          <option value="true">yes</option>
          <option value="false">no</option>
        </select>
      </div>
    </div>
  </fieldset>
</template>
