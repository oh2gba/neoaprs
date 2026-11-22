<script setup lang="ts">
// The one small button for a row or card: delete, close, message (MessageGlyph), path, pin and
// lock (toggles; `pressed` becomes aria-pressed), at least 32 by 32 px. `label` is the
// screen-reader name. `armed` is the first press of a delete (useSure): it shows "sure?" in a
// fixed-width slot (TwoWords) so that nothing moves under the finger.
import MessageGlyph from "@/components/MessageGlyph.vue";
import TwoWords from "@/components/TwoWords.vue";
import { t } from "@/i18n";

withDefaults(
  defineProps<{ kind: "delete" | "close" | "message" | "pin" | "path" | "lock"; label: string; title?: string; armed?: boolean; pressed?: boolean }>(),
  {
    title: undefined,
    armed: false,
    pressed: false,
  },
);
</script>

<template>
  <button
    type="button"
    class="xbtn"
    :class="{ armed: kind === 'delete' && armed, pressed: (kind === 'pin' || kind === 'lock') && pressed }"
    :aria-label="label"
    :aria-pressed="kind === 'pin' || kind === 'lock' ? pressed : undefined"
    :title="
      title ??
      (kind === 'message' || kind === 'path' || kind === 'lock'
        ? label
        : kind === 'delete'
          ? t('iconbutton.delete')
          : kind === 'pin'
            ? t(pressed ? 'iconbutton.unpin' : 'iconbutton.pin')
            : t('iconbutton.close'))
    "
  >
    <MessageGlyph v-if="kind === 'message'" />
    <TwoWords v-else-if="kind === 'delete'" :second="armed">
      <template #first>
        <svg
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
          <path d="M2.5 4h11M6 4V2.5h4V4M4 4l.7 9.5h6.6L12 4M6.8 6.5v4.5M9.2 6.5v4.5" />
        </svg>
      </template>
      <template #second>{{ t("iconbutton.sure") }}</template>
    </TwoWords>
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
      <template v-if="kind === 'pin'">
        <path d="M5.5 2.5h5M6.5 2.5v4.2L4.5 9.2h7L9.5 6.7V2.5" :fill="pressed ? 'currentColor' : 'none'" />
        <path d="M8 9.2v4.3" />
      </template>
      <template v-else-if="kind === 'lock'">
        <rect x="3" y="7" width="10" height="7" rx="1.5" :fill="pressed ? 'currentColor' : 'none'" />
        <path d="M5 7V5a3 3 0 0 1 6 0v2" />
      </template>
      <template v-else-if="kind === 'path'">
        <circle cx="3.5" cy="12" r="1.6" />
        <circle cx="8" cy="4" r="1.6" />
        <circle cx="12.5" cy="12" r="1.6" />
        <path d="M4.3 10.6l2.9-5.2M8.8 5.4l2.9 5.2" />
      </template>
      <path v-else d="M3.5 3.5l9 9M12.5 3.5l-9 9" />
    </svg>
  </button>
</template>
