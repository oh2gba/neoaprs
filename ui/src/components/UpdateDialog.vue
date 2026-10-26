<script setup lang="ts">
// "NeoAPRS 0.7.0 is available": the dialog in the middle of the page, over a dimmed page (the whole screen on a phone), opened by the header's Update mark, the header's badge of a phone and the Settings tab's answer
// to Check now. The version this copy is, what is new (the project's note of the version page, and the release's notes on GitHub as a button), then the update itself: **Update now** where the daemon can
// do it (the topic `update` says so: the Windows installer, an AppImage), with its progress, a Cancel while it downloads and the problem in words when it fails; and the steps by hand for the way this copy
// was installed (lib/update.ts, UpdateSteps), folded under Update now and open when it failed. The focus goes into the dialog and stays in it; Escape, the cross and a click beside it close it, which
// does not stop an update. The longer explanation is in the manual (Updating).
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from "vue";
import IconButton from "@/components/IconButton.vue";
import UpdateSteps from "@/components/UpdateSteps.vue";
import { t } from "@/i18n";
import { useDaemonContext } from "@/composables/useDaemonContext";
import { problemText, progressText, releaseNotes, updateHelp, updateRunning } from "@/lib/update";

const props = defineProps<{ version: string }>();
const { install, version: installed, status, selfUpdate, connection, send } = useDaemonContext();
const emit = defineEmits<{ close: [] }>();

const steps = computed(() => updateHelp(install.value, props.version));
const note = computed(() => status.value?.update?.message ?? "");
/** The daemon can update itself: Update now is offered (and stays while one runs, whatever the topic says after). */
const running = computed(() => updateRunning(selfUpdate.value));
const offered = computed(() => selfUpdate.value?.supported === true || running.value);
const progress = computed(() => (selfUpdate.value ? progressText(selfUpdate.value, install.value?.kind, connection.value === "open") : null));
const failed = computed(() => (selfUpdate.value?.state === "error" ? selfUpdate.value : null));
const cancellable = computed(() => selfUpdate.value?.state === "downloading" || selfUpdate.value?.state === "verifying");

const dialog = ref<HTMLElement | null>(null);
let before: Element | null = null;

function focusables(): HTMLElement[] {
  return [...(dialog.value?.querySelectorAll<HTMLElement>("a[href], button:not([disabled]), summary, [tabindex]:not([tabindex='-1'])") ?? [])];
}

/** Tab and Shift+Tab go round inside the dialog. */
function keepFocus(event: KeyboardEvent): void {
  const items = focusables();
  const first = items[0];
  const last = items[items.length - 1];
  if (!first || !last) return;
  const inside = dialog.value?.contains(document.activeElement) ?? false;
  if (event.shiftKey && (document.activeElement === first || !inside)) {
    event.preventDefault();
    last.focus();
  } else if (!event.shiftKey && (document.activeElement === last || !inside)) {
    event.preventDefault();
    first.focus();
  }
}

function onKey(event: KeyboardEvent): void {
  if (event.key === "Escape" && !event.defaultPrevented) {
    event.preventDefault();
    emit("close");
  } else if (event.key === "Tab") keepFocus(event);
}

onMounted(async () => {
  before = document.activeElement;
  document.addEventListener("keydown", onKey);
  await nextTick();
  (dialog.value?.querySelector<HTMLElement>(".updatedialog-go") ?? dialog.value)?.focus();
});
onBeforeUnmount(() => {
  document.removeEventListener("keydown", onKey);
  if (before instanceof HTMLElement && before.isConnected) before.focus();
});

const updateNow = (): boolean => send({ cmd: "update_now", version: props.version });
const cancel = (): boolean => send({ cmd: "update_cancel" });
</script>

<template>
  <div class="updatedialog-backdrop" @pointerdown.self="emit('close')">
    <section ref="dialog" class="updatedialog" role="dialog" aria-modal="true" aria-labelledby="updatedialog-title" tabindex="-1">
      <header class="updatedialog-head">
        <div class="updatedialog-titles">
          <h2 id="updatedialog-title">{{ t("help.update.title", { version }) }}</h2>
          <p v-if="installed" class="muted updatedialog-installed">{{ t("help.update.installed", { version: installed }) }}</p>
        </div>
        <IconButton kind="close" :label="t('help.close')" @click="emit('close')" />
      </header>
      <section class="updatedialog-news">
        <h3>{{ t("help.update.news") }}</h3>
        <p v-if="note">{{ note }}</p>
        <a class="btn" :href="releaseNotes(version)" target="_blank" rel="noopener noreferrer">{{ t("help.update.news_link", { version }) }}</a>
      </section>
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
    </section>
  </div>
</template>
