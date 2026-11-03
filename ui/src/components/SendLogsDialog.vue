<script setup lang="ts">
// The dialog of Send logs (SettingsHelp opens it), in the middle of the page over a dimmed one as the path builder's is, and with its keys (useDialogFocus: the focus in the text, Tab going round, Esc closing): one text, "What happened?", of a few lines
// and at most NOTE_MAX characters, Send and Cancel. Send hands the words to the group (an empty text is fine) and closes the dialog, and the group does the sending and tells the outcome; Cancel, the cross, Esc and a press beside the dialog close it
// and send nothing. The one (i) in the header says what goes and that nothing goes before Send; no other line explains anything.
import { ref, useId } from "vue";
import IconButton from "@/components/IconButton.vue";
import InfoTip from "@/components/InfoTip.vue";
import { useDialogFocus } from "@/composables/useDialogFocus";
import { t } from "@/i18n";
import { openTip } from "@/lib/infotip";
import { NOTE_MAX } from "@/lib/support";

const props = defineProps<{
  /** the button that opened it, which gets the focus back */
  opener: HTMLElement | null;
}>();
const emit = defineEmits<{ send: [note: string]; close: [] }>();

const titleId = useId();
const noteId = useId();
const dialog = ref<HTMLElement | null>(null);
const note = ref("");
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
      <footer class="logsdialog-foot">
        <button type="button" class="btn primary" @click="emit('send', note.trim())">{{ t("settings.help.dialog.send") }}</button>
        <button type="button" class="btn" @click="emit('close')">{{ t("settings.help.dialog.cancel") }}</button>
      </footer>
    </section>
  </div>
</template>
