<script setup lang="ts">
// The settings of the daemon, one field for every key it lists in the scope of the form (the Settings tab, or the My station tab with the keys the beacon sends), in groups (SettingsGroup; the Settings tab's fold by an arrow in the legend, and a group with a complaint of the daemon opens by itself). There is no Save button: a choice (a list, a switch, a symbol, a place
// picked on the map) applies at once, a typed field on Enter or when it is left (never while it is typed), after the page's own check of it; the daemon checks it again, and a wrong one is shown under its field with what was typed kept. What
// the person sees of it (the Undo toast, a line for a screen reader) is useSettings, shared with the other tab so that there is one queue. The alert command has a Test button, which runs the saved command and shows how it went under the field; a page of another device has neither (the daemon takes the command and runs the Test for a page on its own computer only, and says in hello which this is); a field
// left empty shows the default as a placeholder. The Map group has the Radius row and, under it, the Detailed map row with the button that makes the map (MapFetchButton, plain) and under the button the progress, a failure and "Map downloaded 21 Oct" (MapFetchNotes); they work on the saved settings. Every action that is a row of its own (this one, Check now, Download logs) is an ActionRow. On the Settings tab a link at the top opens the first-run guide again; the default slot is
// for more groups (the page's own, which are not settings of the daemon), the slot `top` for the beacon status above the first group, and `status` for the line with the button that sends the status now, which opens the Status group. The My station tab's Station group
// starts with the choice of where the position comes from (gps/source: Fixed, or a GPS) and what that needs; the place (Location) is shown for Fixed only (with a GPS it stays stored and out of sight), and the Beacon group has the Beacon choice (an interval, or Off and On for a moving station) and, for a moving station, the Travelling choice instead of the antenna. While the beacon is Off the Beacon group's other fields (Travelling, the comment, the antenna, the path) and the whole Status group are shown greyed out (`disabled` of SettingsField), the Station group never. The Radio group is SettingsRadio: the FM radio and the HF radio in a box each, the state of the radio link in view and the fields of the radio behind a fold, and the fields of the page's own alert end the
// Notifications group (BrowserAlerts). What it works on is the page's (useDaemonContext): the settings, the daemon's answers, `send`. The Internet group (the one tickbox, Enable; while it is on, the status row under it, as the radio's; igate/server and igate/password are not on the page) says Set your call first and shows nothing else while the call is not set. The Update check group (the daily check itself is always on) has a Check now button, which asks the version page at once and says the answer in the toast (a newer version opens the update window). While the network is let in, the Web group shows
// the access key with a New key button and the addresses to open the page at. The group Encrypted messages (our key's fingerprint, with a New key button and the (i) that says what the feature is) is there only while the daemon runs with --encryption and so has a key; the Update check group follows, then the Help group (SettingsHelp), and the About group (SettingsAbout) is the last.
import BrowserAlerts from "@/components/BrowserAlerts.vue";
import TwoWords from "@/components/TwoWords.vue";
import ConfirmRow from "@/components/ConfirmRow.vue";
import MapFetchButton from "@/components/MapFetchButton.vue";
import MapFetchNotes from "@/components/MapFetchNotes.vue";
import ActionRow from "@/components/ActionRow.vue";
import DigipeaterStatus from "@/components/DigipeaterStatus.vue";
import IgateStatus from "@/components/IgateStatus.vue";
import UpdateRow from "@/components/UpdateRow.vue";
import { internetStations } from "@/lib/igatestatus";
import InfoTip from "@/components/InfoTip.vue";
import LanguageField from "@/components/LanguageField.vue";
import SettingsField from "@/components/SettingsField.vue";
import SettingsFold from "@/components/SettingsFold.vue";
import SettingsLocation from "@/components/SettingsLocation.vue";
import SettingsBox from "@/components/SettingsBox.vue";
import SettingsAbout from "@/components/SettingsAbout.vue";
import SettingsGroup from "@/components/SettingsGroup.vue";
import SettingsHelp from "@/components/SettingsHelp.vue";
import SettingsHttps from "@/components/SettingsHttps.vue";
import SettingsPort from "@/components/SettingsPort.vue";
import SymbolField from "@/components/SymbolField.vue";
import SettingsRadio from "@/components/SettingsRadio.vue";
import { t } from "@/i18n";
import { useDaemonContext } from "@/composables/useDaemonContext";
import { ALERT_KEY, useAlertTest } from "@/composables/useAlertTest";
import { KEY_KEY, useNewKey } from "@/composables/useNewKey";
import { useSure } from "@/composables/useSure";
import { useUpdateCheck } from "@/composables/useUpdateCheck";
import { fieldId, useSettingsForm } from "@/composables/useSettingsForm";
import type { Picked } from "@/composables/usePositionPick";
import { disabledByValues } from "@/lib/beaconoff";
import { degreesText } from "@/lib/setup";
import { BEACON_FOLDS, SUBGROUPS, fieldFor, igateOn, shownByValues, storedFor, valueFor, type Scope } from "@/lib/settings";
import { shownByRadios, shownFor } from "@/lib/settingsradio";
import { statusSource } from "@/lib/status";
import { statusFrequencyHint } from "@/lib/statusfrequency";
import { computed, watch } from "vue";

const props = withDefaults(defineProps<{ scope?: Scope; picking?: boolean; picked?: Picked | null }>(), { scope: "settings", picking: false, picked: null });
const emit = defineEmits<{ setup: []; update: []; notes: []; pickPosition: [] }>();

const { config, lastError, send, settings, alertResult, updateResult, map, alerts, ports, say, igate, stations, tnc, status, now, keys, local } =
  useDaemonContext();
const newMessageKey = useSure<string>(); // (the New key of encrypted messages asks twice: the stations that have the old key must be sent the new one)
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
const STATUS_TEXT_KEY = "station/status";
const SYMBOL_TABLE = "station/symbol_table";
const SYMBOL_CODE = "station/symbol_code";
const GPS_DEVICE = "gps/device";
const info = (key: string) => fieldFor(key, draft);
/** The quiet line under the status text when it has a frequency that radios would not tune to (the way to write it), else empty. */
function frequencyHint(text: string): string {
  const form = statusFrequencyHint(text);
  return form === null ? "" : t("settings.station_status.hint", { freq: form });
}
/** A field the My station tab greys out while the beacon is Off (shown, with its value, and not changeable). */
const greyed = (key: string): boolean => props.scope === "beacon" && disabledByValues(key, draft);
/** The network is let in and the daemon has made a key (what is in force, not the switch as it is being changed). */
const network = computed(() => config.value?.values["web/network"] === "true" && (config.value.values[KEY_KEY] ?? "") !== "");
const urls = computed(() => config.value?.urls ?? []);
/** Our call in force (the iGate logs in as it, and the page where a passcode is requested is told it); the iGate group asks for it first. */
const call = computed(() => (config.value?.values["station/call"] ?? "").trim());
// the answers of the buttons (Test, New key) are said in the toast, so that nothing moves; the answer of Check now is in its row
watch(
  () => alertTest.result.value,
  (result) => result && say(result.text),
);
watch(
  () => newKey.result.value,
  (result) => result && say(result.text),
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
      (key !== ALERT_KEY || local.value) &&
      shownFor(key, profile.value, network.value) &&
      shownByRadios(key, draft) &&
      shownByValues(key, draft),
  );
/** The groups with something to show: a group whose every key the radios that are on leave out (the Digipeater group while FM is off) is not drawn. */
const drawn = computed(() => groups.value.filter((group) => group.id !== "digi" || shown(group.keys).length > 0));
/** The symbol is one field, which sets the table and the code. */
const symbol = computed(() => `${draft[SYMBOL_TABLE] ?? ""}${draft[SYMBOL_CODE] ?? ""}`);
function editSymbol(text: string): void {
  settings.edit(SYMBOL_TABLE, text.slice(0, 1));
  settings.edit(SYMBOL_CODE, text.slice(1, 2));
}
// a place picked on the map (the My station tab's Choose on map) is our station's latitude and longitude, sent together
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
/** Only the Settings tab folds its groups. */
const folds = props.scope === "settings";
/** A group has something the person must see, so it opens by itself: a complaint of the daemon about one of its fields, or the question it asks about one. */
const needsLook = (groupKeys: readonly string[]): boolean => groupKeys.some((key) => (errors[key] ?? "") !== "" || question.value?.key === key);
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
    <SettingsGroup v-for="group in drawn" :id="group.id" :key="group.id" :title="group.title" :fold="folds" :show="needsLook(group.keys)">
      <SettingsRadio v-if="group.id === 'serial'" :keys="shown(group.keys)" :settings="settings" :form="form" :defaults="defaults" />
      <p v-if="group.id === 'igate' && call === ''" class="problem" role="status">{{ t("settings.igate.set_call") }}</p>
      <SettingsBox
        v-for="box in boxesOf(group.id === 'serial' || (group.id === 'igate' && call === '') ? [] : shown(group.keys))"
        :key="box.id"
        :title="box.sub?.text"
        :hover="box.sub?.title"
      >
        <template v-if="box.sub" #legend>
          <InfoTip :label="box.sub.tipLabel" :picture="box.sub.picture">
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
            :hint="key === STATUS_TEXT_KEY ? frequencyHint(draft[key] ?? '') : ''"
            @update:model-value="typed(key, $event)"
            @choose="form.choose({ [key]: storedFor(key, draft, $event) })"
            @commit="form.finish(key, $event)"
            @cancel="settings.cancel(key)"
          >
            <template v-if="key === ALERT_KEY" #after>
              <button class="btn" type="button" :disabled="alertTest.running.value || alertTest.stale.value" @click="alertTest.test">
                {{ t("settings.alert_test") }}
              </button>
            </template>
            <template v-else-if="key === KEY_KEY" #after>
              <button class="btn" :class="{ danger: newKey.armed.value }" type="button" :disabled="newKey.running.value" @click="newKey.press">
                <TwoWords :second="newKey.armed.value">
                  <template #first>{{ t("settings.new_key") }}</template>
                  <template #second>{{ t("settings.new_key_sure") }}</template>
                </TwoWords>
              </button>
            </template>
          </SettingsField>
          <ActionRow v-if="key === RADIUS_KEY && map" id="set-map-fetch" :label="t('settings.map.detail_label')" :tip-label="t('settings.map.tip_label')">
            <MapFetchButton id="set-map-fetch" :map="map" :stale="settings.saving.value" :send="send" />
            <template #tip
              ><span class="info-line">{{ t("settings.map.tip1") }}</span></template
            >
            <template #notes><MapFetchNotes :map="map" /></template>
          </ActionRow>
          <ConfirmRow v-if="question?.key === key" :message="question.message" @yes="form.answer(true)" @cancel="form.answer(false)" />
          <slot name="after" :field-key="key" :draft="draft"></slot>
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
      <IgateStatus
        v-if="group.id === 'igate' && call !== '' && igate && igateOn(draft)"
        :igate="igate"
        :values="config.values"
        :stations="internetStations(stations.values())"
      />
      <DigipeaterStatus
        v-if="group.id === 'digi' && tnc && draft['digi/enabled'] === 'true'"
        :tnc="tnc"
        :started-at="status?.started_at ?? null"
        :now="now"
        :rx-only="draft['station/transmit'] === 'false'"
      />
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
      <BrowserAlerts v-if="group.id === 'notifications'" :alerts="alerts" :https="config.https" :say="say" />
    </SettingsGroup>
    <SettingsGroup v-if="scope === 'settings' && keys.on.value" id="encrypt" class="encrypt" :title="t('settings.group.encrypt')">
      <ActionRow id="set-message-key" :label="t('settings.encrypt.key_label')" :tip-label="t('settings.encrypt.tip_label')" picture="encrypt">
        <input id="set-message-key" class="input mono" type="text" readonly :value="keys.own.value" />
        <button class="btn" :class="{ danger: newMessageKey.armed.value === 'key' }" type="button" @click="newMessageKey.press('key', () => keys.renew())">
          <TwoWords :second="newMessageKey.armed.value === 'key'">
            <template #first>{{ t("settings.new_key") }}</template>
            <template #second>{{ t("settings.new_key_sure") }}</template>
          </TwoWords>
        </button>
        <template #tip>
          <span class="info-line">{{ t("settings.encrypt.tip1") }}</span>
          <span class="info-line">{{ t("settings.encrypt.tip2") }}</span>
        </template>
      </ActionRow>
    </SettingsGroup>
    <SettingsGroup v-if="scope === 'settings'" id="update" class="update-check" :title="t('settings.update.group')">
      <UpdateRow
        :running="updateCheck.running.value"
        :outcome="updateCheck.outcome.value"
        @check="updateCheck.check"
        @update="emit('update')"
        @notes="emit('notes')"
      />
    </SettingsGroup>
    <SettingsHelp v-if="scope === 'settings'" />
    <SettingsAbout v-if="scope === 'settings'" />
    <slot></slot>
  </form>
  <p v-else class="empty">{{ t("settings.no_word") }}</p>
</template>
