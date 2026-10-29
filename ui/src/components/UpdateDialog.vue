<script setup lang="ts">
// "NeoAPRS 0.7.0 is available": the dialog in the middle of the page, over a dimmed page (the whole screen on a phone), opened by the header's Update mark, the header's badge of a phone and the Settings tab's answer
// to Check now. The version this copy is, what is new (the project's note of the version page, and the release notes themselves: the dialog asks the daemon for them, `release_notes`, and shows the sections of the versions between this one and the new one in a box
// that scrolls; while they are fetched it says so, and when they cannot be it offers the release page on GitHub instead), then the update itself: **Update now** where the daemon can
// do it (the topic `update` says so: the Windows installer, an AppImage), with its progress, a Cancel while it downloads and the problem in words when it fails; and the steps by hand for the way this copy
// was installed (lib/update.ts, UpdateSteps), folded under Update now and open when it failed. The focus goes into the dialog and stays in it; Escape, the cross and a click beside it close it, which
// does not stop an update. The longer explanation is in the manual (Updating).
// The same window in its notes form (`notesOnly`, composables/useWhatsNew.ts), opened from Settings → Update check and from the line the page shows once after an update: "What's new in NeoAPRS 0.12.0", the version that runs, and only
// the notes, of that version or with `since` of every version after that one up to it (the daemon reads them from the changelog at our own tag); no note of the version page, no update, no steps, and the release page when they cannot be fetched.
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import IconButton from "@/components/IconButton.vue";
import UpdateSteps from "@/components/UpdateSteps.vue";
import { t } from "@/i18n";
import { useDaemonContext } from "@/composables/useDaemonContext";
import { useDialogFocus } from "@/composables/useDialogFocus";
import { noteBlocks } from "@/lib/releasenotes";
import { problemText, progressText, releaseNotes, updateHelp, updateRunning } from "@/lib/update";

const props = defineProps<{ version: string; notesOnly?: boolean; since?: string }>();
const { install, version: installed, status, selfUpdate, connection, send, releaseNotes: notesAnswer } = useDaemonContext();
const emit = defineEmits<{ close: [] }>();

const steps = computed(() => updateHelp(install.value, props.version));
const note = computed(() => (props.notesOnly ? "" : (status.value?.update?.message ?? "")));
/** The daemon's answer for this version and this `since`: null while it has not come. */
const notes = computed(() => (notesAnswer.value?.version === props.version && notesAnswer.value.since === (props.since ?? "") ? notesAnswer.value : null));
/** The sections to show, each as blocks; the version of a section heads it when there are several. */
const sections = computed(() => (notes.value?.sections ?? []).map((section) => ({ version: section.version, blocks: noteBlocks(section.text) })));
/** The daemon can update itself: Update now is offered (and stays while one runs, whatever the topic says after). */
const running = computed(() => updateRunning(selfUpdate.value));
const offered = computed(() => selfUpdate.value?.supported === true || running.value);
const progress = computed(() => (selfUpdate.value ? progressText(selfUpdate.value, install.value?.kind, connection.value === "open") : null));
const failed = computed(() => (selfUpdate.value?.state === "error" ? selfUpdate.value : null));
const cancellable = computed(() => selfUpdate.value?.state === "downloading" || selfUpdate.value?.state === "verifying");

const dialog = ref<HTMLElement | null>(null);
const keys = useDialogFocus(dialog, () => emit("close"), { first: () => dialog.value?.querySelector<HTMLElement>(".updatedialog-go") ?? null });

onMounted(() => {
  if (notes.value === null)
    send(props.since ? { cmd: "release_notes", version: props.version, since: props.since } : { cmd: "release_notes", version: props.version });
  document.addEventListener("keydown", keys.onKey);
});
onBeforeUnmount(() => document.removeEventListener("keydown", keys.onKey));

const updateNow = (): boolean => send({ cmd: "update_now", version: props.version });
const cancel = (): boolean => send({ cmd: "update_cancel" });
</script>

<template>
  <div class="updatedialog-backdrop" @pointerdown.self="emit('close')">
    <section ref="dialog" class="updatedialog" role="dialog" aria-modal="true" aria-labelledby="updatedialog-title" tabindex="-1">
      <header class="updatedialog-head">
        <div class="updatedialog-titles">
          <h2 id="updatedialog-title">{{ t(notesOnly ? "help.update.notes_title" : "help.update.title", { version }) }}</h2>
          <p v-if="notesOnly && since" class="muted updatedialog-installed">{{ t("help.update.notes_since", { version: since }) }}</p>
          <p v-else-if="!notesOnly && installed" class="muted updatedialog-installed">{{ t("help.update.installed", { version: installed }) }}</p>
        </div>
        <IconButton kind="close" :label="t('help.close')" @click="emit('close')" />
      </header>
      <section class="updatedialog-news">
        <h3 v-if="!notesOnly">{{ t("help.update.news") }}</h3>
        <p v-if="note">{{ note }}</p>
        <div v-if="sections.length > 0" class="updatedialog-notes">
          <template v-for="section in sections" :key="section.version">
            <h4 v-if="sections.length > 1">{{ section.version }}</h4>
            <template v-for="(block, index) in section.blocks" :key="index">
              <h5 v-if="block.kind === 'heading'">
                <template v-for="(part, i) in block.parts" :key="i">{{ part.text }}</template>
              </h5>
              <ul v-else-if="block.kind === 'bullet'">
                <li>
                  <template v-for="(part, i) in block.parts" :key="i"
                    ><strong v-if="part.bold">{{ part.text }}</strong
                    ><code v-else-if="part.code">{{ part.text }}</code
                    ><template v-else>{{ part.text }}</template></template
                  >
                </li>
              </ul>
              <p v-else>
                <template v-for="(part, i) in block.parts" :key="i"
                  ><strong v-if="part.bold">{{ part.text }}</strong
                  ><code v-else-if="part.code">{{ part.text }}</code
                  ><template v-else>{{ part.text }}</template></template
                >
              </p>
            </template>
          </template>
        </div>
        <template v-else-if="notes !== null">
          <p class="muted">{{ t("help.update.news_failed") }}</p>
          <a class="btn" :href="releaseNotes(version)" target="_blank" rel="noopener noreferrer">{{ t("help.update.news_link", { version }) }}</a>
        </template>
        <p v-else class="muted" role="status">{{ t("help.update.news_loading") }}</p>
      </section>
      <template v-if="!notesOnly">
        <section v-if="offered" class="updatedialog-now">
          <template v-if="progress">
            <p class="updatedialog-progress" role="status">{{ progress }}</p>
            <progress v-if="selfUpdate?.state === 'downloading'" max="100" :value="selfUpdate.percent ?? undefined"></progress>
            <button v-if="cancellable" type="button" class="btn" @click="cancel">{{ t("help.update.cancel") }}</button>
          </template>
          <template v-else>
            <p v-if="failed" class="updatedialog-problem" role="alert" :title="failed.detail">{{ problemText(failed.problem) }}</p>
            <button type="button" class="btn primary updatedialog-go" @click="updateNow">{{ t(failed ? "help.update.retry" : "help.update.now") }}</button>
          </template>
        </section>
        <details v-if="offered" class="updatedialog-hand" :open="failed !== null">
          <summary>{{ t("help.update.by_hand") }}</summary>
          <UpdateSteps :steps="steps" />
        </details>
        <section v-else class="updatedialog-hand">
          <h3>{{ t("help.update.steps") }}</h3>
          <UpdateSteps :steps="steps" />
        </section>
        <p class="muted updatedialog-foot">{{ t("help.update.foot") }}</p>
      </template>
    </section>
  </div>
</template>
