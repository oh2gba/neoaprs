<script setup lang="ts">
// "Route" in the header of a conversation: a button (of the one height of the page's buttons: the header is a toolbar) that opens, in a box under the header, the radio the messages to the station go on (where more than one
// is on), the path they go by and the tickbox RF only (StationPrefs). It is closed until it is pressed, and closed again by Esc, a click or tap outside it, or the focus moving away. A dot on the button says the route is not
// the default one (a radio chosen, a path of its own on the radio in force, or RF only), which the old closed heading said by being open.
import { computed, ref, watch } from "vue";
import StationPrefs from "@/components/StationPrefs.vue";
import { t } from "@/i18n";
import { usePopup } from "@/composables/usePopup";
import { effectivePath } from "@/lib/messages";
import type { PageRadio, RadioId } from "@/lib/radios";

const props = withDefaults(
  defineProps<{
    call: string;
    paths: ReadonlyMap<string, string>;
    fallbackPath: string;
    rfOnly?: ReadonlySet<string>;
    heard?: string | null;
    radios?: readonly PageRadio[];
    choice?: RadioId | null;
    auto?: string | null;
    pathShown?: boolean;
    pathless?: string;
  }>(),
  { rfOnly: () => new Set<string>(), heard: null, radios: () => [], choice: null, auto: null, pathShown: true, pathless: undefined },
);
const emit = defineEmits<{
  path: [call: string, path: string];
  clearPath: [call: string];
  setRfOnly: [call: string, on: boolean];
  radio: [call: string, radio: RadioId | null];
}>();

const open = ref(false);
const root = ref<HTMLElement | null>(null);
const button = ref<HTMLButtonElement | null>(null);
const changed = computed(() => props.choice !== null || effectivePath(props.paths, props.fallbackPath, props.call).own || props.rfOnly.has(props.call));

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
      class="btn route-button"
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
        :radios="radios"
        :choice="choice"
        :auto="auto"
        :path-shown="pathShown"
        :pathless="pathless"
        @path="(c, p) => emit('path', c, p)"
        @clear-path="emit('clearPath', $event)"
        @set-rf-only="(c, on) => emit('setRfOnly', c, on)"
        @radio="(c, radio) => emit('radio', c, radio)"
      />
    </div>
  </div>
</template>
