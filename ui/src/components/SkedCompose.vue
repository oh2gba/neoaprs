<script setup lang="ts">
// Plan a test, the dialog of the Skeds tab (opened by its button or a row's Join) over the dimmed
// page, with useDialogFocus keys: Day (next 30 UTC days), time From and To in half hours (UTC; a To
// not after From is the next day), Frequency (DialChoice: a suggested dial, or Other and the number
// alone) and a one-line Note with a counter. The values are the pane's (`form`, useSkedForm), so a
// dialog closed without posting opens again as it was. Post is on when there is a call, the board
// can be reached and the form is valid (lib/skeds.ts); RX only does not matter. A sked that has
// ended marks the To. When the daemon has the sked the note clears and the dialog closes; a refused
// post leaves it open. Opening it asks for a fresh list of dials (useSkedForm `refresh`). The
// cross, Cancel, Esc and a press beside it close it.
import { computed, ref, useId, watch } from "vue";
import DialChoice from "@/components/DialChoice.vue";
import IconButton from "@/components/IconButton.vue";
import LeftCounter from "@/components/LeftCounter.vue";
import { useDaemonContext } from "@/composables/useDaemonContext";
import { useDialogFocus } from "@/composables/useDialogFocus";
import { useCommandInFlight } from "@/composables/useInFlight";
import { useSkedForm, type SkedForm } from "@/composables/useSkedForm";
import { t } from "@/i18n";
import { leftTitle } from "@/lib/compose";
import { openTip } from "@/lib/infotip";
import { TIMES, NOTE_MAX, draftOk, ended, mayPostAs, postCommand } from "@/lib/skeds";
import { leftOf, type TextLimit, trimmedCharacters, typedInto } from "@/lib/textlimit";

const props = withDefaults(
  defineProps<{
    /** what the pane holds for the form; a dialog of its own without one */
    form?: SkedForm | null;
    /** the button that opened the dialog, which gets the focus back */
    opener?: HTMLElement | null;
  }>(),
  { form: null, opener: null },
);
const emit = defineEmits<{ close: [] }>();

const { skeds, call, now, send } = useDaemonContext();
const { draft, days, frequencies, choose, refresh } = props.form ?? useSkedForm();
/** The characters of the note; the field takes no more (lib/textlimit.ts). */
const limit: TextLimit = { max: NOTE_MAX, measure: trimmedCharacters, kind: "characters" };
const left = computed(() => leftOf(draft.note, limit));
const over = computed(() => ended(draft, now.value));
const ready = computed(() => skeds.value?.state === "ok" && mayPostAs(call.value) && draftOk(draft, now.value));
refresh();

const titleId = useId();
const dialog = ref<HTMLElement | null>(null);
const keys = useDialogFocus(dialog, () => emit("close"), {
  first: () => dialog.value?.querySelector<HTMLElement>("#sked-day") ?? null,
  back: () => props.opener,
});
openTip.value = null;

/** A press on the dimmed page beside the dialog closes it; no press inside goes further. */
function press(event: PointerEvent): void {
  event.stopPropagation();
  if (event.target === event.currentTarget) emit("close");
}

/** Wait for the on-screen keyboard, then scroll the focused field into view (as ComposeBar does). */
function seen(event: FocusEvent): void {
  const field = event.target;
  if (field instanceof HTMLElement) window.setTimeout(() => field.scrollIntoView?.({ block: "nearest" }), 300);
}

// what was posted, until the daemon has it
const asked = ref<{ from: string; to: string; dial: string; note: string } | null>(null);

watch(
  () =>
    asked.value === null
      ? undefined
      : skeds.value?.rows.find(
          (r) => r.ours && r.from === asked.value?.from && r.to === asked.value?.to && r.dial === asked.value?.dial,
        ),
  (row) => {
    const sent = asked.value;
    if (sent === null || row === undefined) return;
    asked.value = null;
    if (draft.note.trim() === sent.note) draft.note = "";
    emit("close");
  },
);

const posting = useCommandInFlight("sked_post", () => skeds.value?.rows);

function submit(): void {
  const command = postCommand(draft, now.value);
  if (command === null || !ready.value) return;
  if (posting.run(() => send(command)))
    asked.value = { from: command.from, to: command.to, dial: command.dial, note: command.note };
}
</script>

<template>
  <div class="skeddialog-backdrop" title="" @pointerdown="press" @focusin.stop @keydown="keys.onKey">
    <section ref="dialog" class="skeddialog" role="dialog" aria-modal="true" :aria-labelledby="titleId" tabindex="-1">
      <header class="updatedialog-head">
        <h2 :id="titleId" class="logsdialog-title">{{ t("skeds.post_label") }}</h2>
        <IconButton kind="close" :label="t('skeds.cancel')" @click="emit('close')" />
      </header>
      <form class="sked-compose" :aria-labelledby="titleId" @submit.prevent="submit" @focusin="seen">
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
            <select
              id="sked-to"
              v-model="draft.to"
              class="input mono"
              :class="{ invalid: over }"
              :aria-label="t('skeds.to')"
            >
              <option v-for="time in TIMES" :key="time" :value="time">{{ time }}</option>
            </select>
          </div>
        </div>
        <DialChoice
          id="sked-frequency"
          dial-id="sked-dial"
          :frequencies="frequencies"
          :typed="draft.typed"
          :dial="draft.dial"
          @choose="choose"
          @update:dial="draft.dial = $event"
        />
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
        <footer class="logsdialog-foot">
          <LeftCounter :left="left" :max="NOTE_MAX" :title="leftTitle(left, 'characters', NOTE_MAX)" />
          <button type="submit" class="btn primary" :disabled="!ready || posting.busy.value">
            {{ t("skeds.post") }}
          </button>
          <button type="button" class="btn" @click="emit('close')">{{ t("skeds.cancel") }}</button>
        </footer>
      </form>
    </section>
  </div>
</template>
