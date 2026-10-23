<script setup lang="ts">
// The settings of the daemon, one field for every key it lists in the scope of the form (the Settings tab, or the Beacon tab with the keys the beacon sends), in groups. Save sends the keys that were changed (the daemon checks them all before it stores any; a wrong one is shown under
// its field); the alert command has a Test button, which runs the saved command and shows how it went under the field; a field left empty shows the default as a placeholder. The Map group ends with the buttons that make
// the map (MapFetchPanel), which work on the saved settings. On the Settings tab the Setup button opens the first-run guide again; the default slot is for more groups (the page's own, which are not settings of the daemon), and the slot `notifications` for the fields of the page's own alert, which end the Notifications group. The Update check group has a Check now button, which asks the version page at once and shows the answer beside it for a few seconds. While the network is let in, the Web group shows the access key with a New key button and the addresses to open the page at.
import MapFetchPanel from "@/components/MapFetchPanel.vue";
import SettingsField from "@/components/SettingsField.vue";
import SettingsPort from "@/components/SettingsPort.vue";
import type { Toast } from "@/composables/useDaemon";
import { ALERT_KEY, useAlertTest } from "@/composables/useAlertTest";
import { KEY_KEY, useNewKey } from "@/composables/useNewKey";
import { useUpdateCheck } from "@/composables/useUpdateCheck";
import { useSettingsForm } from "@/composables/useSettingsForm";
import type { Picked } from "@/composables/usePositionPick";
import { degreesText } from "@/lib/setup";
import { FIELDS, SUBGROUPS, portForProfile, shownFor, speedFallback, type Scope } from "@/lib/settings";
import type { AlertResultMessage, Command, ConfigValues, MapState, PortsMessage, UpdateResultMessage } from "@/protocol/protocol";
import { computed, toRef, watch } from "vue";

const props = withDefaults(
  defineProps<{
    config: ConfigValues | null;
    lastError: Toast | null;
    send: (command: Command) => boolean;
    scope?: Scope;
    alertResult?: AlertResultMessage | null;
    updateResult?: UpdateResultMessage | null;
    map?: MapState | null;
    ports?: PortsMessage | null;
    picking?: boolean;
    picked?: Picked | null;
  }>(),
  { scope: "settings", alertResult: null, updateResult: null, map: null, ports: null, picking: false, picked: null },
);
const emit = defineEmits<{ setup: []; update: []; pickPosition: [] }>();

const { draft, errors, saving, saved, groups, defaults, changed, dirty, save, edit, revert } = useSettingsForm(
  toRef(props, "config"),
  toRef(props, "lastError"),
  (command) => props.send(command),
  props.scope,
);
const alertTest = useAlertTest(
  toRef(props, "alertResult"),
  toRef(props, "lastError"),
  (command) => props.send(command),
  draft,
  computed(() => props.config?.values[ALERT_KEY]),
);
const updateCheck = useUpdateCheck(toRef(props, "updateResult"), toRef(props, "lastError"), (command) => props.send(command));
const newKey = useNewKey();
const info = (key: string) => FIELDS[key] ?? { label: key };
/** The network is let in and the daemon has made a key (what is saved, not the draft of the switch). */
const network = computed(() => props.config?.values["web/network"] === "true" && (props.config.values[KEY_KEY] ?? "") !== "");
const urls = computed(() => props.config?.urls ?? []);
const resultOf = (key: string) => (key === ALERT_KEY ? alertTest.result.value : key === KEY_KEY ? newKey.result.value : null);
/** The TNC profile as it is being edited: which fields are shown follows it. */
const profile = computed(() => draft["tnc/profile"]);
/** Whether the daemon looks for the radio among the ports (Linux); true until it has said. */
const search = computed(() => props.ports?.search ?? true);
const shown = (keys: string[]) => keys.filter((key) => shownFor(key, profile.value, network.value, search.value));
// a place picked on the map (the Beacon tab's Pick on the map) fills our station's latitude and longitude, to be saved like any change
watch(
  () => props.picked,
  (at) => {
    if (!at) return;
    edit("station/lat", degreesText(Math.round(at.lat * 1e5) / 1e5));
    edit("station/lon", degreesText(Math.round((((((at.lon + 180) % 360) + 360) % 360) - 180) * 1e5) / 1e5));
  },
);
const refreshPorts = () => props.send({ cmd: "list_ports" }); // (the page asks for the list itself each time the daemon is connected: App.vue)
const fallback = (key: string) => (key === "serial/baud" ? speedFallback(profile.value, defaults.value[key] ?? "") : (defaults.value[key] ?? ""));
/** A serial device does not go with a TCP profile: choosing one clears it, so that Save is not refused for it. */
function onEdit(key: string, text: string): void {
  edit(key, text);
  if (key === "tnc/profile" && "serial/port" in draft) edit("serial/port", portForProfile(text, draft["serial/port"] ?? ""));
}
/** The map is made for the settings the daemon has: unsaved changes of its keys have to be saved first. */
const mapUnsaved = computed(() => Object.keys(changed.value).some((key) => key.startsWith("map/")));
</script>

<template>
  <form v-if="config" class="settings" novalidate @submit.prevent="save">
    <fieldset v-for="group in groups" :key="group.id">
      <legend>{{ group.title }}</legend>
      <template v-for="key in shown(group.keys)" :key="key">
        <h3 v-if="SUBGROUPS[key]" class="subgroup" :title="SUBGROUPS[key]?.title">{{ SUBGROUPS[key]?.text }}</h3>
        <SettingsPort
          v-if="key === 'serial/port'"
          :id="`set-${key.replace('/', '-')}`"
          :info="info(key)"
          :model-value="draft[key] ?? ''"
          :found="config.values['serial/last_port'] ?? ''"
          :ports="ports"
          :error="errors[key] ?? ''"
          :changed="key in changed"
          @update:model-value="onEdit(key, $event)"
          @refresh="refreshPorts"
        />
        <SettingsField
          v-else
          :id="`set-${key.replace('/', '-')}`"
          :info="info(key)"
          :model-value="draft[key] ?? ''"
          :fallback="fallback(key)"
          :error="errors[key] ?? ''"
          :changed="key in changed"
          :result="resultOf(key)"
          @update:model-value="onEdit(key, $event)"
        >
          <template v-if="key === 'station/lon' && scope === 'beacon'" #after>
            <button class="btn" type="button" :class="{ active: picking }" @click="emit('pickPosition')">{{ picking ? "Cancel" : "Pick on the map" }}</button>
          </template>
          <template v-else-if="key === ALERT_KEY" #after>
            <button
              class="btn"
              type="button"
              :disabled="alertTest.running.value || alertTest.stale.value"
              :title="alertTest.stale.value ? 'Save first' : undefined"
              @click="alertTest.test"
            >
              Test
            </button>
          </template>
          <template v-else-if="key === 'update/check'" #after>
            <button class="btn" type="button" :disabled="updateCheck.running.value" @click="updateCheck.check">Check now</button>
            <template v-if="updateCheck.outcome.value">
              <button v-if="updateCheck.outcome.value.newer" class="updatecheck-result" type="button" role="status" @click="emit('update')">
                {{ updateCheck.outcome.value.text }}
              </button>
              <span v-else class="updatecheck-result muted" role="status">{{ updateCheck.outcome.value.text }}</span>
            </template>
          </template>
          <template v-else-if="key === KEY_KEY" #after>
            <button class="btn" :class="{ danger: newKey.armed.value }" type="button" :disabled="newKey.running.value" @click="newKey.press">
              {{ newKey.armed.value ? "sure?" : "New key" }}
            </button>
          </template>
        </SettingsField>
        <div v-if="key === KEY_KEY && urls.length" class="field">
          <label for="set-web-url-0">Open at</label>
          <div class="field-control urls">
            <input v-for="(url, i) in urls" :id="`set-web-url-${i}`" :key="url" class="input" type="text" readonly :value="url" />
          </div>
        </div>
      </template>
      <slot v-if="group.id === 'notifications'" name="notifications"></slot>
      <MapFetchPanel v-if="group.id === 'map' && map" :map="map" :stale="mapUnsaved" :send="props.send" />
    </fieldset>
    <slot></slot>
    <slot name="preview" :draft="draft"></slot>
    <div class="settings-actions">
      <button class="btn primary" type="submit" :disabled="!dirty || saving">{{ saving ? "Saving..." : "Save" }}</button>
      <button class="btn" type="button" :disabled="!dirty" @click="revert">Revert</button>
      <button v-if="scope === 'settings'" class="btn setup-open" type="button" @click="emit('setup')">Setup</button>
      <span v-if="saved && !dirty" class="muted" role="status">Saved.</span>
      <span v-else-if="dirty" class="muted">{{ Object.keys(changed).length }} changed</span>
    </div>
  </form>
  <p v-else class="empty">No word from the daemon yet.</p>
</template>
