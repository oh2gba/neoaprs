<script setup lang="ts">
// The settings of the daemon, one field for every key it lists in the scope of the form (the Settings tab, or the Beacon tab with the keys the beacon sends), in groups. There is no Save button: a choice (a list, a switch, a symbol, a place
// picked on the map) applies at once, a typed field on Enter or when it is left (never while it is typed), after the page's own check of it; the daemon checks it again, and a wrong one is shown under its field with what was typed kept. What
// the person sees of it (the Undo toast, a line for a screen reader) is useSettings, shared with the other tab so that there is one queue. The alert command has a Test button, which runs the saved command and shows how it went under the field; a field
// left empty shows the default as a placeholder. The Radius row of the Map group has the button that makes the map at its right end (MapFetchButton, plain, as the Test button of the Command row is) and under it the progress, a failure and "Map downloaded 21 Oct" (MapFetchNotes); they work on the saved settings. On the Settings tab a link at the top opens the first-run guide again; the default slot is
// for more groups (the page's own, which are not settings of the daemon), the slot `top` for the beacon status above the first group, and `status` for the line with the button that sends the status now, which opens the Status group. The Beacon tab's Station group
// starts with the choice of where the position comes from (gps/source: Fixed, or a GPS) and what that needs; the place (Location) is shown for Fixed only (with a GPS it stays stored and out of sight), and the Beacon group has the Beacon choice (an interval, or Off and On for a moving station) and, for a moving station, the Travelling choice instead of the antenna. While the beacon is Off the Beacon group's other fields (Travelling, the comment, the antenna, the path) and the whole Status group are shown greyed out (`disabled` of SettingsField), the Station group never. The TNC group is SettingsRadio: the state of the radio link with Reconnect in view and the fields of the radio behind a fold, and the fields of the page's own alert end the
// Notifications group (BrowserAlerts). What it works on is the page's (useDaemonContext): the settings, the daemon's answers, `send`. The iGate group (the switch, the passcode with a link to the page where one is requested, the status line, and what it never does; igate/server is not on the page) says Set your call first and shows nothing else while the call is not set. The Update check group (the daily check itself is always on) has a Check now button, which asks the version page at once and says the answer in the toast (a newer version opens the update window). While the network is let in, the Web group shows
// the access key with a New key button and the addresses to open the page at. The Help group (SettingsHelp) follows the Update check group, and the About group (SettingsAbout) is the last.
import BrowserAlerts from "@/components/BrowserAlerts.vue";
import ConfirmRow from "@/components/ConfirmRow.vue";
import MapFetchButton from "@/components/MapFetchButton.vue";
import MapFetchNotes from "@/components/MapFetchNotes.vue";
import IgateStatus from "@/components/IgateStatus.vue";
import InfoTip from "@/components/InfoTip.vue";
import LanguageField from "@/components/LanguageField.vue";
import SettingsField from "@/components/SettingsField.vue";
import SettingsFold from "@/components/SettingsFold.vue";
import SettingsLocation from "@/components/SettingsLocation.vue";
import SettingsBox from "@/components/SettingsBox.vue";
import SettingsAbout from "@/components/SettingsAbout.vue";
import SettingsHelp from "@/components/SettingsHelp.vue";
import SettingsHttps from "@/components/SettingsHttps.vue";
import SettingsPort from "@/components/SettingsPort.vue";
import SymbolField from "@/components/SymbolField.vue";
import SettingsRadio from "@/components/SettingsRadio.vue";
import { t } from "@/i18n";
import { useDaemonContext } from "@/composables/useDaemonContext";
import { ALERT_KEY, useAlertTest } from "@/composables/useAlertTest";
import { KEY_KEY, useNewKey } from "@/composables/useNewKey";
import { useUpdateCheck } from "@/composables/useUpdateCheck";
import { fieldId, useSettingsForm } from "@/composables/useSettingsForm";
import type { Picked } from "@/composables/usePositionPick";
import { disabledByValues } from "@/lib/beaconoff";
import { degreesText } from "@/lib/setup";
import { BEACON_FOLDS, SUBGROUPS, fieldFor, shownByValues, shownFor, valueFor, type Scope } from "@/lib/settings";
import { passcodeLink } from "@/lib/igatestatus";
import { statusSource } from "@/lib/status";
import { computed, watch } from "vue";

const props = withDefaults(defineProps<{ scope?: Scope; picking?: boolean; picked?: Picked | null }>(), { scope: "settings", picking: false, picked: null });
const emit = defineEmits<{ setup: []; update: []; pickPosition: [] }>();

const { config, lastError, send, settings, alertResult, updateResult, map, alerts, ports, say, igate, now } = useDaemonContext();
const { draft, errors } = settings;
const form = useSettingsForm(config, settings, props.scope);
const { groups, question, defaults } = form;
const alertTest = useAlertTest(
  alertResult,
  lastError,
  send,
  draft,
  computed(() => config.value?.values[ALERT_KEY]),
);
const updateCheck = useUpdateCheck(updateResult, lastError, send);
const newKey = useNewKey();
const RADIUS_KEY = "map/radius_km";
const SYMBOL_TABLE = "station/symbol_table";
const SYMBOL_CODE = "station/symbol_code";
const GPS_DEVICE = "gps/device";
const info = (key: string) => fieldFor(key, draft);
/** A field the Beacon tab greys out while the beacon is Off (shown, with its value, and not changeable). */
const greyed = (key: string): boolean => props.scope === "beacon" && disabledByValues(key, draft);
/** The network is let in and the daemon has made a key (what is in force, not the switch as it is being changed). */
const network = computed(() => config.value?.values["web/network"] === "true" && (config.value.values[KEY_KEY] ?? "") !== "");
const urls = computed(() => config.value?.urls ?? []);
/** Our call in force (the iGate logs in as it, and the page where a passcode is requested is told it); the iGate group asks for it first. */
const call = computed(() => (config.value?.values["station/call"] ?? "").trim());
// the answers of the buttons (Test, New key, Check now) are said in the toast, so that nothing moves; a newer version opens the update window
watch(
  () => alertTest.result.value,
  (result) => result && say(result.text),
);
watch(
  () => newKey.result.value,
  (result) => result && say(result.text),
);
watch(
  () => updateCheck.outcome.value,
  (outcome) => (outcome?.newer ? emit("update") : outcome && say(outcome.text)),
);
/** The TNC profile as it is being edited: which fields are shown follows it. */
const profile = computed(() => draft["tnc/profile"]);
/** The keys the Beacon group keeps behind closed headings (the antenna, the path): they are not in the group's own list. */
const folded = new Set(props.scope === "beacon" ? BEACON_FOLDS.flatMap((fold) => fold.keys) : []);
const shown = (keys: readonly string[], inGroup = true) =>
  keys.filter(
    (key) =>
      key !== SYMBOL_CODE &&
      !(key === "station/lon" && props.scope === "beacon") &&
      !(inGroup && folded.has(key)) &&
      shownFor(key, profile.value, network.value) &&
      (props.scope === "settings" || shownByValues(key, draft)),
  );
/** The symbol is one field, which sets the table and the code. */
const symbol = computed(() => `${draft[SYMBOL_TABLE] ?? ""}${draft[SYMBOL_CODE] ?? ""}`);
function editSymbol(text: string): void {
  settings.edit(SYMBOL_TABLE, text.slice(0, 1));
  settings.edit(SYMBOL_CODE, text.slice(1, 2));
}
// a place picked on the map (the Beacon tab's Choose on map) is our station's latitude and longitude, sent together
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
const fallback = (key: string) => defaults.value[key] ?? "";
/** The keys of a group in boxes: a key with a heading of its own (the daemon's alert) starts a box with its legend that runs to the end of the group; the keys before it are in no box. */
function boxesOf(keys: readonly string[]) {
  const boxes: { id: string; sub: (typeof SUBGROUPS)[string] | null; keys: string[] }[] = [];
  for (const key of keys) {
    const sub = SUBGROUPS[key] ?? null;
    if (sub !== null || boxes.length === 0) boxes.push({ id: key, sub, keys: [key] });
    else boxes[boxes.length - 1]?.keys.push(key);
  }
  return boxes;
}
/** A typed field follows the typing; a choice is made by `choose` (it also says the text it has, which is not typing). */
function typed(key: string, text: string): void {
  const kind = info(key).kind;
  if (kind !== "bool" && kind !== "choice") settings.edit(key, text);
}
</script>

<template>
  <form v-if="config" class="settings" novalidate @submit.prevent>
    <LanguageField v-if="scope === 'settings'" />
    <p v-if="scope === 'settings'" class="settings-setup">
      <button class="linkbutton setup-open" type="button" @click="emit('setup')">{{ t("settings.setup_again") }}</button>
    </p>
    <span class="sr-only" role="status" aria-live="polite"
      ><span :key="settings.announcement.value.n">{{ settings.announcement.value.text }}</span></span
    >
    <slot name="top"></slot>
    <fieldset v-for="group in groups" :key="group.id">
      <legend>{{ group.title }}</legend>
      <SettingsRadio v-if="group.id === 'serial'" :keys="shown(group.keys)" :settings="settings" :form="form" :defaults="defaults" />
      <slot v-if="group.id === 'status'" name="status"></slot>
      <p v-if="group.id === 'igate' && call === ''" class="problem" role="status">{{ t("settings.igate.set_call") }}</p>
      <IgateStatus v-else-if="group.id === 'igate' && igate" :igate="igate" :values="config.values" :now="now" />
      <SettingsBox
        v-for="box in boxesOf(group.id === 'serial' || (group.id === 'igate' && call === '') ? [] : shown(group.keys))"
        :key="box.id"
        :title="box.sub?.text"
        :hover="box.sub?.title"
      >
        <template v-if="box.sub" #legend>
          <InfoTip :label="box.sub.tipLabel">
            <span v-for="line in box.sub.tip" :key="line" class="info-line">{{ line }}</span>
          </InfoTip>
        </template>
        <template v-for="key in box.keys" :key="key">
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
            v-else-if="key === GPS_DEVICE"
            :id="fieldId(key)"
            :info="info(key)"
            :model-value="draft[key] ?? ''"
            found=""
            :unset="true"
            :ports="ports"
            :error="errors[key] ?? ''"
            :changed="form.changed(key)"
            @update:model-value="settings.edit(key, $event)"
            @choose="form.choose({ [key]: $event })"
            @commit="form.finish(key, $event)"
            @cancel="settings.cancel(key)"
            @refresh="send({ cmd: 'list_ports' })"
          />
          <SettingsField
            v-else
            :id="fieldId(key)"
            :info="info(key)"
            :model-value="key === 'status/source' ? statusSource(draft) : valueFor(key, draft)"
            :fallback="fallback(key)"
            :error="errors[key] ?? ''"
            :changed="form.changed(key)"
            :apply="true"
            :disabled="greyed(key)"
            @update:model-value="typed(key, $event)"
            @choose="form.choose({ [key]: $event })"
            @commit="form.finish(key, $event)"
            @cancel="settings.cancel(key)"
          >
            <template v-if="key === ALERT_KEY" #after>
              <button class="btn" type="button" :disabled="alertTest.running.value || alertTest.stale.value" @click="alertTest.test">
                {{ t("settings.alert_test") }}
              </button>
            </template>
            <template v-else-if="key === RADIUS_KEY && map" #after>
              <MapFetchButton v-if="map" :map="map" :stale="settings.saving.value" :send="send" />
            </template>
            <template v-else-if="key === 'igate/password'" #after>
              <a class="btn igate-request" :href="passcodeLink(call)" target="_blank" rel="noopener">{{ t("settings.igate.request") }}</a>
            </template>
            <template v-else-if="key === KEY_KEY" #after>
              <button class="btn" :class="{ danger: newKey.armed.value }" type="button" :disabled="newKey.running.value" @click="newKey.press">
                {{ newKey.armed.value ? t("settings.new_key_sure") : t("settings.new_key") }}
              </button>
            </template>
          </SettingsField>
          <MapFetchNotes v-if="key === RADIUS_KEY && map" :map="map" />
          <ConfirmRow v-if="question?.key === key" :message="question.message" @yes="form.answer(true)" @cancel="form.answer(false)" />
          <SettingsHttps v-if="key === 'web/https'" :https="config.https" />
          <div v-if="key === KEY_KEY && urls.length" class="field">
            <label for="set-web-url-0">{{ t("settings.urls.label") }}</label>
            <div class="field-control">
              <div class="urls">
                <input v-for="(url, i) in urls" :id="`set-web-url-${i}`" :key="url" class="input" type="text" readonly :value="url" />
              </div>
              <InfoTip :label="t('settings.urls.tip_label')">
                <span class="info-line">{{ t("settings.urls.tip1") }}</span>
                <span class="info-line">{{ t("settings.urls.tip2") }}</span>
              </InfoTip>
            </div>
          </div>
        </template>
      </SettingsBox>
      <template v-if="scope === 'beacon'">
        <SettingsFold
          v-for="fold in BEACON_FOLDS.filter((f) => f.group === group.id)"
          :key="fold.title"
          :title="fold.title"
          :keys="shown(fold.keys, false)"
          :settings="settings"
          :form="form"
          :defaults="defaults"
          :disabled="greyed"
        />
      </template>
      <p v-if="group.id === 'igate'" class="igate-note">{{ t("settings.igate.note") }}</p>
      <BrowserAlerts v-if="group.id === 'notifications'" :alerts="alerts" :https="config.https" :say="say" />
    </fieldset>
    <fieldset v-if="scope === 'settings'" class="update-check">
      <legend>{{ t("settings.update.group") }}</legend>
      <div class="field">
        <label for="set-update-now">{{ t("settings.update.label") }}</label>
        <div class="field-control">
          <button id="set-update-now" class="btn" type="button" :disabled="updateCheck.running.value" @click="updateCheck.check">
            {{ t("settings.update.check") }}
          </button>
          <InfoTip :label="t('settings.update.tip_label')">
            <span class="info-line">{{ t("settings.update.tip") }}</span>
          </InfoTip>
        </div>
      </div>
    </fieldset>
    <SettingsHelp v-if="scope === 'settings'" />
    <SettingsAbout v-if="scope === 'settings'" />
    <slot></slot>
    <slot name="preview" :draft="draft"></slot>
  </form>
  <p v-else class="empty">{{ t("settings.no_word") }}</p>
</template>
