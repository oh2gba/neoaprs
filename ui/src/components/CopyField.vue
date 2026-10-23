<script setup lang="ts">
// A text the person has to type somewhere else (an address, a command), in a box that selects with one click, with a Copy button that says Copied for a moment.
import { onBeforeUnmount, ref } from "vue";
import { t } from "@/i18n";
import { copyText } from "@/lib/clipboard";

const props = defineProps<{ text: string }>();

const state = ref<"help.copy" | "help.copied" | "help.not_copied">("help.copy");
let timer: ReturnType<typeof setTimeout> | undefined;

async function copy(): Promise<void> {
  state.value = (await copyText(props.text)) ? "help.copied" : "help.not_copied";
  clearTimeout(timer);
  timer = setTimeout(() => (state.value = "help.copy"), 2000);
}
onBeforeUnmount(() => clearTimeout(timer));
</script>

<template>
  <span class="copyfield">
    <code class="mono">{{ text }}</code>
    <button type="button" class="btn small" @click="copy">{{ t(state) }}</button>
  </span>
</template>
