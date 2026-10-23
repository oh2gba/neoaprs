<script setup lang="ts">
// "Update to 0.4.0": opened from the new version in the header. A link to what is new (in the page's link colour), and the steps for the way this copy was installed (lib/update.ts; the way is not named: the steps say it): a command has a button that copies it, a file a link that downloads it. Escape and the cross close it.
// The longer explanation of each way is in the manual (Updating).
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import IconButton from "@/components/IconButton.vue";
import { t } from "@/i18n";
import { useDaemonContext } from "@/composables/useDaemonContext";
import { copyText } from "@/lib/clipboard";
import { releaseNotes, updateHelp } from "@/lib/update";

const props = defineProps<{ version: string }>();
const { install } = useDaemonContext();
const emit = defineEmits<{ close: [] }>();

const help = computed(() => updateHelp(install.value, props.version));
/** The command whose button was pressed last, and how it went. */
const copied = ref<{ command: string; ok: boolean } | null>(null);
let timer: ReturnType<typeof setTimeout> | undefined;

async function copy(command: string): Promise<void> {
  copied.value = { command, ok: await copyText(command) };
  clearTimeout(timer);
  timer = setTimeout(() => (copied.value = null), 2000);
}
const label = (command: string): string => t(copied.value?.command !== command ? "help.copy" : copied.value.ok ? "help.copied" : "help.not_copied");

function onKey(event: KeyboardEvent): void {
  if (event.key === "Escape" && !event.defaultPrevented) emit("close");
}
onMounted(() => document.addEventListener("keydown", onKey));
onBeforeUnmount(() => {
  document.removeEventListener("keydown", onKey);
  clearTimeout(timer);
});
</script>

<template>
  <section class="updatepanel" role="dialog" :aria-label="t('help.update.title', { version })">
    <header class="updatepanel-head">
      <h2>{{ t("help.update.title", { version }) }}</h2>
      <IconButton kind="close" :label="t('help.close')" @click="emit('close')" />
    </header>
    <p class="updatepanel-news">
      <a :href="releaseNotes(version)" target="_blank" rel="noopener noreferrer">{{ t("help.update.news") }}</a>
    </p>
    <ol class="updatepanel-steps">
      <li v-for="step in help.steps" :key="step.text + (step.command ?? '')">
        <span>{{ step.text }}</span>
        <a v-if="step.link" class="updatepanel-file" :href="step.link.href" target="_blank" rel="noopener noreferrer">{{ step.link.label }}</a>
        <span v-if="step.command" class="updatepanel-command">
          <code class="mono">{{ step.command }}</code>
          <button type="button" class="btn small" @click="copy(step.command)">{{ label(step.command) }}</button>
        </span>
      </li>
    </ol>
    <p class="muted updatepanel-foot">{{ t("help.update.foot") }}</p>
  </section>
</template>
