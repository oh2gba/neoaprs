<script setup lang="ts">
// The dialog of Send feedback / logs (opened by SettingsHelp), with useDialogFocus keys: one text
// of up to NOTE_MAX characters, an optional address for a reply, the logs file shown as an attachment,
// Send and Cancel. Send hands the words, the address and whether the file goes to the group, which
// does the sending, and closes the dialog. The dialog starts from the group's `draft`, `email` and
// `attached` and reports every change so that what was not sent returns at the next opening. The file's name downloads it (useSupportLogs.collect); the
// group holds that download so that Send names the very file the person looked at. The × takes the
// file off (it stays in place, dimmed, and the × becomes Attach); both faces are in the page
// (TwoWords), so nothing moves. Send is off until there are words, while the download runs and while
// the address is not one (the field's border says so). The line under the file says what the
// download did.
import { computed, ref, useId, watch } from "vue";
import IconButton from "@/components/IconButton.vue";
import TwoWords from "@/components/TwoWords.vue";
import { useDialogFocus } from "@/composables/useDialogFocus";
import type { SupportLogs } from "@/composables/useSupportLogs";
import { t } from "@/i18n";
import { openTip } from "@/lib/infotip";
import { EMAIL_MAX, NOTE_MAX, replyAddressOk } from "@/lib/support";

const props = withDefaults(
  defineProps<{
    /** the button that opened the dialog, which gets the focus back */
    opener: HTMLElement | null;
    /** the download of the file, which the group holds */
    download: Pick<SupportLogs, "running" | "saved" | "problem" | "collect">;
    /**
     * our call, which names the logs file (neoaprs/cli/supportbundle.py, bundle_name: `nocall`
     * without one)
     */
    call?: string | null;
    /** the words written at an earlier opening and not sent */
    draft?: string;
    /** the address for a reply typed at an earlier opening and not sent */
    email?: string;
    /** whether the file goes with the words: false when an earlier opening took it off */
    attached?: boolean;
  }>(),
  { call: null, draft: "", email: "", attached: true },
);
const emit = defineEmits<{
  send: [note: string, file: boolean, email: string];
  draft: [text: string];
  email: [text: string];
  attached: [on: boolean];
  close: [];
}>();

const titleId = useId();
const noteId = useId();
const emailId = useId();
const dialog = ref<HTMLElement | null>(null);
/** The words written, from the group's draft; the group keeps them until sent. */
const note = ref(props.draft);
watch(note, (text) => emit("draft", text), { flush: "sync" });
const email = ref(props.email);
watch(email, (text) => emit("email", text), { flush: "sync" });
const address = computed(() => email.value.trim());
const addressBad = computed(() => address.value !== "" && !replyAddressOk(address.value));
/** The name the file is shown by. */
const name = computed(() => `neoaprs-support-${props.call || "nocall"}.zip`);
const on = ref(props.attached);
watch(on, (now) => emit("attached", now), { flush: "sync" });
const sendable = computed(
  () => !props.download.running.value && !addressBad.value && (on.value || note.value.trim() !== ""),
);
const keys = useDialogFocus(dialog, () => emit("close"), {
  first: () => dialog.value?.querySelector<HTMLElement>("textarea") ?? null,
  back: () => props.opener,
});
openTip.value = null;

/** A press on the dimmed page beside the dialog closes it; no press inside goes further. */
function press(event: PointerEvent): void {
  event.stopPropagation();
  if (event.target === event.currentTarget) emit("close");
}
</script>

<template>
  <div class="logsdialog-backdrop" title="" @pointerdown="press" @focusin.stop @keydown="keys.onKey">
    <section ref="dialog" class="logsdialog" role="dialog" aria-modal="true" :aria-labelledby="titleId" tabindex="-1">
      <header class="updatedialog-head">
        <h2 :id="titleId" class="logsdialog-title">{{ t("settings.help.dialog.title") }}</h2>
        <IconButton kind="close" :label="t('settings.help.dialog.cancel')" @click="emit('close')" />
      </header>
      <label :for="noteId" class="logsdialog-label">{{ t("settings.help.dialog.label") }}</label>
      <textarea
        :id="noteId"
        v-model="note"
        class="input area"
        rows="5"
        :maxlength="NOTE_MAX"
        :placeholder="t('settings.help.dialog.placeholder')"
      ></textarea>
      <label :for="emailId" class="logsdialog-label">{{ t("settings.help.dialog.email") }}</label>
      <input
        :id="emailId"
        v-model="email"
        class="input"
        :class="{ invalid: addressBad }"
        type="email"
        autocomplete="email"
        spellcheck="false"
        :maxlength="EMAIL_MAX"
        :aria-invalid="addressBad"
      />
      <div
        class="logsdialog-attached"
        :class="{ off: !on }"
        role="group"
        :aria-label="on ? t('settings.help.dialog.attached') : undefined"
      >
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
        <button
          type="button"
          class="linkbtn logsdialog-file"
          :disabled="!on || download.running.value"
          :aria-busy="download.running.value"
          :aria-label="on ? t('settings.help.dialog.download', { file: name }) : undefined"
          :title="on ? t('settings.help.dialog.download', { file: name }) : undefined"
          @click="download.collect"
        >
          {{ name }}
        </button>
        <button
          type="button"
          class="logsdialog-x"
          :aria-label="on ? t('settings.help.dialog.remove', { file: name }) : undefined"
          :title="on ? t('settings.help.dialog.remove', { file: name }) : undefined"
          @click="on = !on"
        >
          <TwoWords :second="!on">
            <template #first>×</template>
            <template #second>{{ t("settings.help.dialog.attach") }}</template>
          </TwoWords>
        </button>
      </div>
      <p class="logsdialog-status" role="status">
        <template v-if="download.running.value">{{ t("settings.help.collecting") }}</template>
        <template v-else-if="download.saved.value !== null">{{
          t("settings.help.saved", { file: download.saved.value })
        }}</template>
        <span v-else-if="download.problem.value" class="field-error">{{ download.problem.value }}</span>
      </p>
      <footer class="logsdialog-foot">
        <button type="button" class="btn primary" :disabled="!sendable" @click="emit('send', note.trim(), on, address)">
          {{ t("settings.help.dialog.send") }}
        </button>
        <button type="button" class="btn" @click="emit('close')">{{ t("settings.help.dialog.cancel") }}</button>
      </footer>
    </section>
  </div>
</template>
