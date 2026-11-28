<script setup lang="ts">
// The steps of an update by hand (made by lib/update.ts for the way this copy was installed):
// text, a file or page as a button, and a command with a copy button. Steps are numbered; where
// they are ways of which one is taken (`either`), the others lead in and the ways are bullets.
import { computed, onBeforeUnmount, ref } from "vue";
import { t } from "@/i18n";
import { copyText } from "@/lib/clipboard";
import type { Step } from "@/lib/update";

const props = defineProps<{ steps: Step[] }>();

const ways = computed(() => props.steps.filter((step) => step.either));
const lead = computed(() => (ways.value.length === 0 ? [] : props.steps.filter((step) => !step.either)));
const listed = computed(() => (ways.value.length === 0 ? props.steps : ways.value));

/** The command whose button was pressed last, and how it went. */
const copied = ref<{ command: string; ok: boolean } | null>(null);
let timer: ReturnType<typeof setTimeout> | undefined;

async function copy(command: string): Promise<void> {
  copied.value = { command, ok: await copyText(command) };
  clearTimeout(timer);
  timer = setTimeout(() => (copied.value = null), 2000);
}
const label = (command: string): string =>
  t(copied.value?.command !== command ? "help.copy" : copied.value.ok ? "help.copied" : "help.not_copied");
onBeforeUnmount(() => clearTimeout(timer));
</script>

<template>
  <p v-for="step in lead" :key="step.text" class="updatesteps-lead">{{ step.text }}</p>
  <component :is="ways.length === 0 ? 'ol' : 'ul'" class="updatesteps">
    <li v-for="step in listed" :key="step.text + (step.command ?? '')">
      <span>{{ step.text }}</span>
      <a
        v-if="step.link"
        class="btn updatesteps-file"
        :href="step.link.href"
        target="_blank"
        rel="noopener noreferrer"
        >{{ step.link.label }}</a
      >
      <span v-if="step.command" class="updatesteps-command">
        <code class="mono">{{ step.command }}</code>
        <button type="button" class="btn small" @click="copy(step.command)">{{ label(step.command) }}</button>
      </span>
    </li>
  </component>
</template>
