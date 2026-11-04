<script setup lang="ts">
// The dialog of Send feedback / logs (SettingsHelp opens it), in the middle of the page over a dimmed one as the path builder's is, and with its keys (useDialogFocus: the focus in the text, Tab going round, Esc closing): one text, "What happened?", of a few lines
// and at most NOTE_MAX characters, Send and Cancel. Send hands the words to the group (an empty text is fine) and closes the dialog, and the group does the sending and tells the outcome; Cancel, the cross, Esc and a press beside the dialog close it
// and send nothing. Under the text the logs file is shown attached, as a mail program shows an attachment (its name as the daemon makes it, without the time it is made at). The one (i) in the header says
// what goes and that nothing goes before Send; no other line explains anything.
import { computed, ref, useId } from "vue";
import IconButton from "@/components/IconButton.vue";
import InfoTip from "@/components/InfoTip.vue";
import { useDialogFocus } from "@/composables/useDialogFocus";
import { t } from "@/i18n";
import { openTip } from "@/lib/infotip";
import { NOTE_MAX } from "@/lib/support";

const props = defineProps<{
  /** the button that opened it, which gets the focus back */
  opener: HTMLElement | null;
  /** our call, which names the logs file (neoaprs/cli/supportbundle.py, bundle_name: `nocall` without one) */
  call?: string | null;
}>();
const emit = defineEmits<{ send: [note: string]; close: [] }>();

const titleId = useId();
const noteId = useId();
const dialog = ref<HTMLElement | null>(null);
const note = ref("");
const attached = computed(() => `neoaprs-support-${props.call || "nocall"}.zip`);
const keys = useDialogFocus(dialog, () => emit("close"), {
  first: () => dialog.value?.querySelector<HTMLElement>("textarea") ?? null,
  back: () => props.opener,
});

/** A press on the dimmed page beside the dialog closes it; no press in it goes further, and one outside the (i) closes its note. */
function press(event: PointerEvent): void {
  event.stopPropagation();
  if (!(event.target instanceof Element && event.target.closest(".infotip"))) openTip.value = null;
  if (event.target === event.currentTarget) emit("close");
}

/** Esc with the (i)'s note open closes the note only. */
function escapeNote(event: KeyboardEvent): void {
  if (event.key !== "Escape" || openTip.value === null) return;
  event.stopPropagation();
  openTip.value = null;
}
</script>

<template>
  <div class="logsdialog-backdrop" title="" @pointerdown="press" @focusin.stop @keydown.capture="escapeNote" @keydown="keys.onKey">
    <section ref="dialog" class="logsdialog" role="dialog" aria-modal="true" :aria-labelledby="titleId" tabindex="-1">
      <header class="updatedialog-head">
        <h2 :id="titleId" class="logsdialog-title">{{ t("settings.help.dialog.title") }}</h2>
        <InfoTip class="logsdialog-tip" :label="t('settings.help.dialog.tip_label')">
          <span class="info-line">{{ t("settings.help.dialog.tip") }}</span>
          <span class="info-line">{{ t("settings.help.dialog.tip2") }}</span>
        </InfoTip>
        <IconButton kind="close" :label="t('settings.help.dialog.cancel')" @click="emit('close')" />
      </header>
      <label :for="noteId" class="logsdialog-label">{{ t("settings.help.dialog.label") }}</label>
      <textarea :id="noteId" v-model="note" class="input area" rows="5" :maxlength="NOTE_MAX"></textarea>
      <p class="logsdialog-attached" :aria-label="t('settings.help.dialog.attached')">
        <svg class="logsdialog-clip" viewBox="0 0 16 16" width="16" height="16" aria-hidden="true">
          <path
            d="M10.5 4.5 5.6 9.4a1.6 1.6 0 0 0 2.3 2.3l5.2-5.2a3 3 0 0 0-4.3-4.3L3.4 7.6a4.4 4.4 0 0 0 6.2 6.2l4.2-4.2"
            fill="none"
            stroke="currentColor"
            stroke-width="1.3"
            stroke-linecap="round"
            stroke-linejoin="round"
          />
        </svg>
        <span class="logsdialog-file">{{ attached }}</span>
      </p>
      <footer class="logsdialog-foot">
        <button type="button" class="btn primary" @click="emit('send', note.trim())">{{ t("settings.help.dialog.send") }}</button>
        <button type="button" class="btn" @click="emit('close')">{{ t("settings.help.dialog.cancel") }}</button>
      </footer>
    </section>
  </div>
</template>
