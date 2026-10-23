<script setup lang="ts">
// The one small button for taking something away: a trash can for "delete", a cross for "close", always at least 32 by 32 pixels so that a finger hits it. `label` is what a screen reader says (it names the thing), the hover title is "Delete"
// or "Close" unless `title` says more (what a delete does on the air). `armed` is the first press of a button that asks twice (useSure): it says "sure?" until the second press.
import { t } from "@/i18n";

withDefaults(defineProps<{ kind: "delete" | "close"; label: string; title?: string; armed?: boolean }>(), { title: undefined, armed: false });
</script>

<template>
  <button
    type="button"
    class="xbtn"
    :class="{ armed }"
    :aria-label="label"
    :title="title ?? (kind === 'delete' ? t('iconbutton.delete') : t('iconbutton.close'))"
  >
    <template v-if="armed">{{ t("iconbutton.sure") }}</template>
    <svg
      v-else
      width="16"
      height="16"
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      stroke-width="1.5"
      stroke-linecap="round"
      stroke-linejoin="round"
      aria-hidden="true"
    >
      <path v-if="kind === 'delete'" d="M2.5 4h11M6 4V2.5h4V4M4 4l.7 9.5h6.6L12 4M6.8 6.5v4.5M9.2 6.5v4.5" />
      <path v-else d="M3.5 3.5l9 9M12.5 3.5l-9 9" />
    </svg>
  </button>
</template>
