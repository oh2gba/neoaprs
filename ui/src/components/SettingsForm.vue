<script setup lang="ts">
// The settings of the daemon, one field for every key it lists in the scope of the form (the Settings tab, or the Beacon tab with the keys the beacon sends), in groups. There is no Save button: a choice (a list, a switch, a symbol, a place
// picked on the map) applies at once, a typed field on Enter or when it is left (never while it is typed), after the page's own check of it; the daemon checks it again, and a wrong one is shown under its field with what was typed kept. What
// the person sees of it (the Undo toast, a line for a screen reader) is useSettings, shared with the other tab so that there is one queue. The alert command has a Test button, which runs the saved command and shows how it went under the field; a field
// left empty shows the default as a placeholder. The Map group ends with the buttons that make the map (MapFetchPanel), which work on the saved settings. On the Settings tab a link at the top opens the first-run guide again; the default slot is
// for more groups (the page's own, which are not settings of the daemon), the slot `radio` for the state of the radio link, which opens the TNC group, the slots `beacon` and `status` for the line with the button that sends it now, which open the Beacon and Status groups, and the slot `notifications` for the fields of the page's own alert, which end the
// Notifications group. The Update check group (the daily check itself is always on) has a Check now button, which asks the version page at once and shows the answer beside it for a few seconds. While the network is let in, the Web group shows
// the access key with a New key button and the addresses to open the page at.
import ConfirmRow from "@/components/ConfirmRow.vue";
import MapFetchPanel from "@/components/MapFetchPanel.vue";
import InfoTip from "@/components/InfoTip.vue";
import SettingsField from "@/components/SettingsField.vue";
import SettingsFold from "@/components/SettingsFold.vue";
import SettingsLocation from "@/components/SettingsLocation.vue";
import SettingsHttps from "@/components/SettingsHttps.vue";
import SymbolField from "@/components/SymbolField.vue";
import SettingsPort from "@/components/SettingsPort.vue";
import type { Toast } from "@/composables/useDaemon";
import { ALERT_KEY, useAlertTest } from "@/composables/useAlertTest";
import { KEY_KEY, useNewKey } from "@/composables/useNewKey";
import { useUpdateCheck } from "@/composables/useUpdateCheck";
import { useSettings, type Settings } from "@/composables/useSettings";
import { fieldId, useSettingsForm } from "@/composables/useSettingsForm";
import type { Picked } from "@/composables/usePositionPick";
import { degreesText } from "@/lib/setup";
import { BEACON_FOLDS, FIELDS, SUBGROUPS, shownByValues, shownFor, speedFallback, type Scope } from "@/lib/settings";
import { statusSource } from "@/lib/status";
import type { AlertResultMessage, Command, ConfigValues, MapState, PortsMessage, UpdateResultMessage } from "@/protocol/protocol";
import { computed, toRef, watch } from "vue";

const props = withDefaults(
  defineProps<{
    config: ConfigValues | null;
    lastError: Toast | null;
    send: (command: Command) => boolean;
    scope?: Scope;
    /** the settings that apply as they are changed, shared with the other tab; the form makes its own if the page gives none */
    settings?: Settings | null;
    alertResult?: AlertResultMessage | null;
    updateResult?: UpdateResultMessage | null;
    map?: MapState | null;
    ports?: PortsMessage | null;
    picking?: boolean;
    picked?: Picked | null;
  }>(),
  { scope: "settings", settings: null, alertResult: null, updateResult: null, map: null, ports: null, picking: false, picked: null },
);
const emit = defineEmits<{ setup: []; update: []; pickPosition: [] }>();

const settings = props.settings ?? useSettings(toRef(props, "config"), toRef(props, "lastError"), (command) => props.send(command));
const { draft, errors } = settings;
const form = useSettingsForm(toRef(props, "config"), settings, props.scope);
const { groups, question, defaults } = form;
const alertTest = useAlertTest(
  toRef(props, "alertResult"),
  toRef(props, "lastError"),
  (command) => props.send(command),
  draft,
  computed(() => props.config?.values[ALERT_KEY]),
);
const updateCheck = useUpdateCheck(toRef(props, "updateResult"), toRef(props, "lastError"), (command) => props.send(command));
const newKey = useNewKey();
const SYMBOL_TABLE = "station/symbol_table";
const SYMBOL_CODE = "station/symbol_code";
const info = (key: string) => FIELDS[key] ?? { label: key };
/** The network is let in and the daemon has made a key (what is in force, not the switch as it is being changed). */
const network = computed(() => props.config?.values["web/network"] === "true" && (props.config.values[KEY_KEY] ?? "") !== "");
const urls = computed(() => props.config?.urls ?? []);
const resultOf = (key: string) => (key === ALERT_KEY ? alertTest.result.value : key === KEY_KEY ? newKey.result.value : null);
/** The TNC profile as it is being edited: which fields are shown follows it. */
const profile = computed(() => draft["tnc/profile"]);
/** Whether the daemon looks for the radio among the ports (Linux); true until it has said. */
const search = computed(() => props.ports?.search ?? true);
/** The keys the Beacon group keeps behind closed headings (the antenna, the path): they are not in the group's own list. */
const folded = new Set(props.scope === "beacon" ? BEACON_FOLDS.flatMap((fold) => fold.keys) : []);
const shown = (keys: readonly string[], inGroup = true) =>
  keys.filter(
    (key) =>
      key !== SYMBOL_CODE &&
      !(key === "station/lon" && props.scope === "beacon") &&
      !(inGroup && folded.has(key)) &&
      shownFor(key, profile.value, network.value, search.value) &&
      (props.scope === "settings" || shownByValues(key, draft)),
  );
/** The symbol is one field, which sets the table and the code. */
const symbol = computed(() => `${draft[SYMBOL_TABLE] ?? ""}${draft[SYMBOL_CODE] ?? ""}`);
function editSymbol(text: string): void {
  settings.edit(SYMBOL_TABLE, text.slice(0, 1));
  settings.edit(SYMBOL_CODE, text.slice(1, 2));
}
// a place picked on the map (the Beacon tab's Pick on the map) is our station's latitude and longitude, sent together
watch(
  () => props.picked,
  (at) => {
    if (!at) return;
    settings.change({
      "station/lat": degreesText(Math.round(at.lat * 1e5) / 1e5),
      "station/lon": degreesText(Math.round((((((at.lon + 180) % 360) + 360) % 360) - 180) * 1e5) / 1e5),
    });
  },
);
const refreshPorts = () => props.send({ cmd: "list_ports" }); // (the page asks for the list itself each time the daemon is connected: App.vue)
const fallback = (key: string) => (key === "serial/baud" ? speedFallback(profile.value, defaults.value[key] ?? "") : (defaults.value[key] ?? ""));
/** A typed field follows the typing; a choice is made by `choose` (it also says the text it has, which is not typing). */
function typed(key: string, text: string): void {
  const kind = info(key).kind;
  if (kind !== "bool" && kind !== "choice") settings.edit(key, text);
}
</script>

<template>
  <form v-if="config" class="settings" novalidate @submit.prevent>
    <p v-if="scope === 'settings'" class="settings-setup">
      <button class="linkbutton setup-open" type="button" @click="emit('setup')">Run the setup guide again</button>
    </p>
    <span class="sr-only" role="status" aria-live="polite"
      ><span :key="settings.announcement.value.n">{{ settings.announcement.value.text }}</span></span
    >
    <fieldset v-for="group in groups" :key="group.id">
      <legend>{{ group.title }}</legend>
      <slot v-if="group.id === 'serial'" name="radio"></slot>
      <slot v-if="group.id === 'beacon'" name="beacon"></slot>
      <slot v-if="group.id === 'status'" name="status"></slot>
      <template v-for="key in shown(group.keys)" :key="key">
        <h3 v-if="SUBGROUPS[key]" class="subgroup" :title="SUBGROUPS[key]?.title">
          {{ SUBGROUPS[key]?.text }}
          <InfoTip :label="SUBGROUPS[key]?.tipLabel ?? ''">
            <span v-for="line in SUBGROUPS[key]?.tip" :key="line" class="info-line">{{ line }}</span>
          </InfoTip>
        </h3>
        <SettingsLocation
          v-if="key === 'station/lat'"
          :draft="draft"
          :current="{ lat: config.values['station/lat'] ?? '', lon: config.values['station/lon'] ?? '' }"
          :errors="errors"
          :changed="form.changed"
          :picking="picking"
          @type="settings.edit"
          @commit="form.finish"
          @cancel="settings.cancel"
          @pick="emit('pickPosition')"
        />
        <SymbolField
          v-else-if="key === SYMBOL_TABLE"
          id="set-station-symbol"
          :symbol="symbol"
          :changed="form.changed(SYMBOL_TABLE) || form.changed(SYMBOL_CODE)"
          @update:symbol="editSymbol"
          @commit="settings.commit([SYMBOL_TABLE, SYMBOL_CODE], true)"
        />
        <SettingsPort
          v-else-if="key === 'serial/port'"
          :id="fieldId(key)"
          :info="info(key)"
          :model-value="draft[key] ?? ''"
          :found="config.values['serial/last_port'] ?? ''"
          :ports="ports"
          :error="errors[key] ?? ''"
          :changed="form.changed(key)"
          @update:model-value="settings.edit(key, $event)"
          @choose="form.choose({ [key]: $event })"
          @commit="form.finish(key, $event)"
          @cancel="settings.cancel(key)"
          @refresh="refreshPorts"
        />
        <SettingsField
          v-else
          :id="fieldId(key)"
          :info="info(key)"
          :model-value="key === 'status/source' ? statusSource(draft) : (draft[key] ?? '')"
          :fallback="fallback(key)"
          :error="errors[key] ?? ''"
          :changed="form.changed(key)"
          :result="resultOf(key)"
          :apply="true"
          @update:model-value="typed(key, $event)"
          @choose="form.choose({ [key]: $event })"
          @commit="form.finish(key, $event)"
          @cancel="settings.cancel(key)"
        >
          <template v-if="key === ALERT_KEY" #after>
            <button class="btn" type="button" :disabled="alertTest.running.value || alertTest.stale.value" @click="alertTest.test">Test</button>
          </template>
          <template v-else-if="key === KEY_KEY" #after>
            <button class="btn" :class="{ danger: newKey.armed.value }" type="button" :disabled="newKey.running.value" @click="newKey.press">
              {{ newKey.armed.value ? "sure?" : "New key" }}
            </button>
          </template>
        </SettingsField>
        <ConfirmRow v-if="question?.key === key" :message="question.message" @yes="form.answer(true)" @cancel="form.answer(false)" />
        <SettingsHttps v-if="key === 'web/https'" :https="config.https" />
        <div v-if="key === KEY_KEY && urls.length" class="field">
          <label for="set-web-url-0">Open at</label>
          <div class="field-control">
            <div class="urls">
              <input v-for="(url, i) in urls" :id="`set-web-url-${i}`" :key="url" class="input" type="text" readonly :value="url" />
            </div>
            <InfoTip label="About the addresses">
              <span class="info-line">Type one of these in the browser of the laptop or phone, which must be on the same network as NeoAPRS.</span>
              <span class="info-line"
                >The one with numbers works everywhere on the network. The one ending in .local is easier to remember and works on most phones and
                laptops.</span
              >
            </InfoTip>
          </div>
        </div>
      </template>
      <template v-if="group.id === 'beacon' && scope === 'beacon'">
        <SettingsFold
          v-for="fold in BEACON_FOLDS"
          :key="fold.title"
          :title="fold.title"
          :keys="shown(fold.keys, false)"
          :settings="settings"
          :form="form"
          :defaults="defaults"
        />
      </template>
      <slot v-if="group.id === 'notifications'" name="notifications"></slot>
      <MapFetchPanel v-if="group.id === 'map' && map" :map="map" :stale="settings.saving.value" :send="props.send" />
    </fieldset>
    <fieldset v-if="scope === 'settings'" class="update-check">
      <legend>Update check</legend>
      <div class="field">
        <label for="set-update-now">New version</label>
        <div class="field-control">
          <button id="set-update-now" class="btn" type="button" :disabled="updateCheck.running.value" @click="updateCheck.check">Check now</button>
          <template v-if="updateCheck.outcome.value">
            <button v-if="updateCheck.outcome.value.newer" class="updatecheck-result" type="button" role="status" @click="emit('update')">
              {{ updateCheck.outcome.value.text }}
            </button>
            <span v-else class="updatecheck-result muted" role="status">{{ updateCheck.outcome.value.text }}</span>
          </template>
          <InfoTip label="About the update check">
            <span class="info-line"
              >Once a day NeoAPRS asks the project's version page whether a newer version is out, and tells you in the footer when there is one.</span
            >
          </InfoTip>
        </div>
      </div>
    </fieldset>
    <slot></slot>
    <slot name="preview" :draft="draft"></slot>
  </form>
  <p v-else class="empty">No word from the daemon yet.</p>
</template>
