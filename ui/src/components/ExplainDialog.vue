<script setup lang="ts">
// A dialog that explains one thing (the pair of radios, the suggested frequencies) over the dimmed
// page, in the frame of Send logs' dialog: a title with the cross, then the slot. Focus goes in on
// open and back to `opener` on close (useDialogFocus); Esc, the cross or a press beside it closes.
import { ref, useId } from "vue";
import IconButton from "@/components/IconButton.vue";
import { useDialogFocus } from "@/composables/useDialogFocus";
import { t } from "@/i18n";
import { openTip } from "@/lib/infotip";

const props = defineProps<{ title: string; opener: HTMLElement | null }>();
const emit = defineEmits<{ close: [] }>();

const titleId = useId();
const dialog = ref<HTMLElement | null>(null);
const keys = useDialogFocus(dialog, () => emit("close"), { back: () => props.opener });
openTip.value = null;

/** A press on the dimmed page beside the dialog closes it; no press inside goes further. */
function press(event: PointerEvent): void {
  event.stopPropagation();
  if (event.target === event.currentTarget) emit("close");
}
</script>

<template>
  <div class="explaindialog-backdrop" @pointerdown="press" @focusin.stop @keydown="keys.onKey">
    <section
      ref="dialog"
      class="explaindialog"
      role="dialog"
      aria-modal="true"
      :aria-labelledby="titleId"
      tabindex="-1"
    >
      <header class="updatedialog-head">
        <h2 :id="titleId" class="explaindialog-title">{{ title }}</h2>
        <IconButton kind="close" :label="t('settings.explain.close')" @click="emit('close')" />
      </header>
      <slot></slot>
    </section>
  </div>
</template>
