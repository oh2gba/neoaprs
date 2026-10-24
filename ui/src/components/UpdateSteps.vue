<script setup lang="ts">
// The numbered steps of an update by hand (lib/update.ts makes them for the way this copy was installed): a line of words, a file or a page as a button, a command with a button that copies it.
import { onBeforeUnmount, ref } from "vue";
import { t } from "@/i18n";
import { copyText } from "@/lib/clipboard";
import type { Step } from "@/lib/update";

defineProps<{ steps: Step[] }>();

/** The command whose button was pressed last, and how it went. */
const copied = ref<{ command: string; ok: boolean } | null>(null);
let timer: ReturnType<typeof setTimeout> | undefined;

async function copy(command: string): Promise<void> {
  copied.value = { command, ok: await copyText(command) };
  clearTimeout(timer);
  timer = setTimeout(() => (copied.value = null), 2000);
}
const label = (command: string): string => t(copied.value?.command !== command ? "help.copy" : copied.value.ok ? "help.copied" : "help.not_copied");
onBeforeUnmount(() => clearTimeout(timer));
</script>

<template>
  <ol class="updatesteps">
    <li v-for="step in steps" :key="step.text + (step.command ?? '')">
      <span>{{ step.text }}</span>
      <a v-if="step.link" class="btn updatesteps-file" :href="step.link.href" target="_blank" rel="noopener noreferrer">{{ step.link.label }}</a>
      <span v-if="step.command" class="updatesteps-command">
        <code class="mono">{{ step.command }}</code>
        <button type="button" class="btn small" @click="copy(step.command)">{{ label(step.command) }}</button>
      </span>
    </li>
  </ol>
</template>
