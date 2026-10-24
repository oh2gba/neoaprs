<script setup lang="ts">
// "Route" in the header of a conversation: a small button that opens the path the messages to the station go by and the tickbox RF only (StationPrefs) in a box under the header. It is closed until it is pressed, and closed again by Esc, a click or
// tap outside it, or the focus moving away. A dot on the button says the route is not the default one (a path of its own, or RF only), which the old closed heading said by being open.
import { computed, ref, watch } from "vue";
import StationPrefs from "@/components/StationPrefs.vue";
import { t } from "@/i18n";
import { usePopup } from "@/composables/usePopup";
import { effectivePath } from "@/lib/messages";

const props = withDefaults(
  defineProps<{ call: string; paths: ReadonlyMap<string, string>; fallbackPath: string; rfOnly?: ReadonlySet<string>; heard?: string | null }>(),
  { rfOnly: () => new Set<string>(), heard: null },
);
const emit = defineEmits<{ path: [call: string, path: string]; clearPath: [call: string]; setRfOnly: [call: string, on: boolean] }>();

const open = ref(false);
const root = ref<HTMLElement | null>(null);
const button = ref<HTMLButtonElement | null>(null);
const changed = computed(() => effectivePath(props.paths, props.fallbackPath, props.call).own || props.rfOnly.has(props.call));

/** Esc closes the box and is not passed on (on a narrow page it would also go back to the list). */
const popup = usePopup({ open, root, trigger: button, close: () => (open.value = false), stopEscape: true });
watch(
  () => props.call,
  () => (open.value = false),
);
</script>

<template>
  <div ref="root" class="routemenu" @keydown="popup.onEscape">
    <button
      ref="button"
      type="button"
      class="btn small route-button"
      :class="{ changed }"
      :aria-expanded="open"
      :title="changed ? t('route.changed') : t('route.button')"
      @click="open = !open"
    >
      {{ t("route.button") }}<span v-if="changed" class="route-dot" aria-hidden="true"></span>
    </button>
    <div v-if="open" class="route-box">
      <StationPrefs
        :call="call"
        :paths="paths"
        :fallback-path="fallbackPath"
        :rf-only="rfOnly"
        :heard="heard"
        @path="(c, p) => emit('path', c, p)"
        @clear-path="emit('clearPath', $event)"
        @set-rf-only="(c, on) => emit('setRfOnly', c, on)"
      />
    </div>
  </div>
</template>
