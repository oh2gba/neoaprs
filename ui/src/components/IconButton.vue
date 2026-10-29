<script setup lang="ts">
// The one small button for a row or a card: a trash can for "delete", a cross for "close", an envelope for "message" (MessageGlyph, the one picture of a message everywhere on the page), a route of three hops for "path" (the path builder of a path field), a pin for "pin" (a toggle: `pressed` says whether it is on, shown to a screen reader as aria-pressed and by the filled pin), always at least 32 by 32 pixels so that a finger hits it. `label` is what a screen reader says (it names the thing),
// the hover title is "Delete" or "Close" ("Pin card" or "Unpin card" for a pin) unless `title` says more (what a delete does on the air); a "message" and a "path" button's is its label ("Message OH2XYZ", "Build the path"). `armed` is the first press of a button that asks twice (useSure): it says "sure?" until the second press.
import MessageGlyph from "@/components/MessageGlyph.vue";
import { t } from "@/i18n";

withDefaults(defineProps<{ kind: "delete" | "close" | "message" | "pin" | "path"; label: string; title?: string; armed?: boolean; pressed?: boolean }>(), {
  title: undefined,
  armed: false,
  pressed: false,
});
</script>

<template>
  <button
    type="button"
    class="xbtn"
    :class="{ armed, pressed: kind === 'pin' && pressed }"
    :aria-label="label"
    :aria-pressed="kind === 'pin' ? pressed : undefined"
    :title="
      title ??
      (kind === 'message' || kind === 'path'
        ? label
        : kind === 'delete'
          ? t('iconbutton.delete')
          : kind === 'pin'
            ? t(pressed ? 'iconbutton.unpin' : 'iconbutton.pin')
            : t('iconbutton.close'))
    "
  >
    <template v-if="armed">{{ t("iconbutton.sure") }}</template>
    <MessageGlyph v-else-if="kind === 'message'" />
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
      <template v-else-if="kind === 'path'">
        <circle cx="3.5" cy="12" r="1.6" />
        <circle cx="8" cy="4" r="1.6" />
        <circle cx="12.5" cy="12" r="1.6" />
        <path d="M4.3 10.6l2.9-5.2M8.8 5.4l2.9 5.2" />
      </template>
      <path v-else-if="kind === 'delete'" d="M2.5 4h11M6 4V2.5h4V4M4 4l.7 9.5h6.6L12 4M6.8 6.5v4.5M9.2 6.5v4.5" />
      <path v-else d="M3.5 3.5l9 9M12.5 3.5l-9 9" />
    </svg>
  </button>
</template>
