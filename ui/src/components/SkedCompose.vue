<script setup lang="ts">
// The group box to post a sked, at the bottom of the Skeds tab (ComposeBar, as everywhere; the fields are rows like those of the Objects form): the Day (the next 30 UTC days, written in the language of the page), the time from and to in
// half hours (the label says UTC; a To that is not after From is the next day), the Frequency (one the project suggests, or Other, which brings a row to type one in the form `7.0541 MHz USB`, as the Category of an object brings its own) and
// the Note, one line with the characters it has left. Post is on when there is a call, the board can be reached and the form is right (lib/skeds.ts); RX only does not matter, nothing here is sent by radio. A sked that has ended already
// marks the To. The note is cleared when the daemon has the sked (the topic `skeds` tells it); a post it refused stays for the user to correct. The dials are the station's (the project's list, the same in every HF radio's
// box): when the Frequency row comes on show (at most once a minute), the daemon is asked to look at the project's list again (`frequencies`), as the box does; a row that came on show before the socket was open asks when it opens.
import { computed, reactive, ref, watch } from "vue";
import ComposeBar from "@/components/ComposeBar.vue";
import { useDaemonContext } from "@/composables/useDaemonContext";
import { useWhenShown } from "@/composables/useWhenShown";
import { t } from "@/i18n";
import { leftTitle } from "@/lib/compose";
import { TIMES, NOTE_MAX, dayChoices, draftDial, draftOk, ended, mayPostAs, postCommand, startDraft, utcDay } from "@/lib/skeds";
import { leftOf, type TextLimit, trimmedCharacters, typedInto } from "@/lib/textlimit";

const { skeds, call, now, send, connection } = useDaemonContext();
const frequencies = computed(() => skeds.value?.frequencies ?? []);
const draft = reactive(startDraft(now.value, frequencies.value));
const days = computed(() => dayChoices(now.value));
const OTHER = "other";
/** The Frequency choice: a dial the project suggests (when it is the one in the draft), else Other. */
const choice = computed(() => (draft.typed ? OTHER : draft.dial));
const placeholder = computed(() => frequencies.value[0]?.dial ?? "7.0541 MHz USB");
/** The characters of the note; the field takes no more (lib/textlimit.ts, as every field with a counter). */
const limit: TextLimit = { max: NOTE_MAX, measure: trimmedCharacters, kind: "characters" };
const left = computed(() => leftOf(draft.note, limit));
const over = computed(() => ended(draft, now.value));
const typedWrong = computed(() => draft.typed && draft.dial.trim() !== "" && draftDial(draft) === null);
const ready = computed(() => skeds.value?.state === "ok" && mayPostAs(call.value) && draftOk(draft, now.value));
const frequencyRow = ref<HTMLElement | null>(null);
let missed = false; // the row came on show before the socket was open: it is asked when the socket opens
const ask = (): void => void (connection.value === "open" ? send({ cmd: "frequencies" }) : (missed = true));
useWhenShown(frequencyRow, ask);
watch(connection, (now) => {
  if (now !== "open" || !missed) return;
  missed = false;
  ask();
});

/** The day goes on being one of the choices as the UTC day turns. */
watch(days, (list) => {
  if (!list.some((d) => d.value === draft.day)) draft.day = utcDay(now.value);
});
/** The dial the project suggests first stands in until one is chosen (the list arrives after the form is made, and is told again with every change of the board). */
let chosen = false;
watch(frequencies, (list) => {
  if (chosen || list[0] === undefined) return;
  draft.typed = false;
  draft.dial = list[0].dial;
});

function choose(value: string): void {
  chosen = true;
  draft.typed = value === OTHER;
  draft.dial = value === OTHER ? "" : value;
}

const asked = ref<{ from: string; to: string; dial: string; note: string } | null>(null); // what was posted, until the daemon has it

watch(
  () =>
    asked.value === null
      ? undefined
      : skeds.value?.rows.find((r) => r.ours && r.from === asked.value?.from && r.to === asked.value?.to && r.dial === asked.value?.dial),
  (row) => {
    const sent = asked.value;
    if (sent === null || row === undefined) return;
    asked.value = null;
    if (draft.note.trim() === sent.note) draft.note = "";
  },
);

function submit(): void {
  const command = postCommand(draft, now.value);
  if (command === null || !ready.value) return;
  asked.value = { from: command.from, to: command.to, dial: command.dial, note: command.note };
  send(command);
}
</script>

<template>
  <ComposeBar
    class="sked-compose"
    :label="t('skeds.post_label')"
    :left="left"
    :left-max="NOTE_MAX"
    :left-title="leftTitle(left, 'characters', NOTE_MAX)"
    @submit="submit"
  >
    <div class="field">
      <label for="sked-day">{{ t("skeds.day") }}</label>
      <div class="field-control">
        <select id="sked-day" v-model="draft.day" class="input">
          <option v-for="d in days" :key="d.value" :value="d.value">{{ d.label }}</option>
        </select>
      </div>
    </div>
    <div class="field">
      <label for="sked-from">{{ t("skeds.time") }}</label>
      <div class="field-control">
        <select id="sked-from" v-model="draft.from" class="input mono" :aria-label="t('skeds.from')">
          <option v-for="time in TIMES" :key="time" :value="time">{{ time }}</option>
        </select>
        <span class="muted">{{ t("skeds.until") }}</span>
        <select id="sked-to" v-model="draft.to" class="input mono" :class="{ invalid: over }" :aria-label="t('skeds.to')">
          <option v-for="time in TIMES" :key="time" :value="time">{{ time }}</option>
        </select>
      </div>
    </div>
    <div ref="frequencyRow" class="field">
      <label for="sked-frequency">{{ t("skeds.frequency") }}</label>
      <div class="field-control">
        <select id="sked-frequency" class="input" :value="choice" @change="choose(($event.target as HTMLSelectElement).value)">
          <option v-for="f in frequencies" :key="f.band" :value="f.dial">{{ `${f.dial} (${f.band})` }}</option>
          <option :value="OTHER">{{ t("skeds.frequency_other") }}</option>
        </select>
      </div>
    </div>
    <div v-if="draft.typed" class="field" :class="{ invalid: typedWrong }">
      <label for="sked-dial">{{ t("skeds.dial") }}</label>
      <div class="field-control">
        <input
          id="sked-dial"
          v-model="draft.dial"
          class="input mono"
          :class="{ invalid: typedWrong }"
          type="text"
          :placeholder="placeholder"
          autocomplete="off"
          spellcheck="false"
        />
      </div>
    </div>
    <div class="field">
      <label for="sked-note">{{ t("skeds.note") }}</label>
      <div class="field-control">
        <input
          id="sked-note"
          :value="draft.note"
          class="input"
          type="text"
          autocomplete="off"
          @input="draft.note = typedInto($event, draft.note, limit)"
          @compositionend="draft.note = typedInto($event, draft.note, limit)"
        />
      </div>
    </div>
    <template #buttons>
      <button type="submit" class="btn primary" :disabled="!ready">{{ t("skeds.post") }}</button>
    </template>
  </ComposeBar>
</template>
