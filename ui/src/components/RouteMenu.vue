<script setup lang="ts">
// "Route" in the header of a conversation: a small button that opens the path the messages to the station go by and the tickbox RF only (StationPrefs) in a box under the header. It is closed until it is pressed, and closed again by Esc, a click or
// tap outside it, or the focus moving away. A dot on the button says the route is not the default one (a path of its own, or RF only), which the old closed heading said by being open.
import { computed, onBeforeUnmount, ref, watch } from "vue";
import StationPrefs from "@/components/StationPrefs.vue";
import { effectivePath } from "@/lib/messages";

const props = withDefaults(
  defineProps<{ call: string; paths: ReadonlyMap<string, string>; fallbackPath: string; rfOnly?: ReadonlySet<string>; suggested?: string | null }>(),
  { rfOnly: () => new Set<string>(), suggested: null },
);
const emit = defineEmits<{ path: [call: string, path: string]; clearPath: [call: string]; setRfOnly: [call: string, on: boolean] }>();

const open = ref(false);
const root = ref<HTMLElement | null>(null);
const button = ref<HTMLButtonElement | null>(null);
const changed = computed(() => effectivePath(props.paths, props.fallbackPath, props.call).own || props.rfOnly.has(props.call));

function away(event: Event): void {
  if (!(event.target instanceof Node) || !root.value?.contains(event.target)) open.value = false;
}

/** Esc closes the box and is not passed on (on a narrow page it would also go back to the list). */
function onKey(event: KeyboardEvent): void {
  if (event.key !== "Escape" || !open.value) return;
  event.stopPropagation();
  open.value = false;
  button.value?.focus();
}

function listen(on: boolean): void {
  const act = (type: string, handler: EventListener): void => (on ? document.addEventListener(type, handler) : document.removeEventListener(type, handler));
  act("pointerdown", away);
  act("focusin", away);
}

watch(open, listen);
watch(
  () => props.call,
  () => (open.value = false),
);
onBeforeUnmount(() => listen(false));
</script>

<template>
  <div ref="root" class="routemenu" @keydown="onKey">
    <button
      ref="button"
      type="button"
      class="btn small route-button"
      :class="{ changed }"
      :aria-expanded="open"
      :title="changed ? 'Route: not the default' : 'Route'"
      @click="open = !open"
    >
      Route<span v-if="changed" class="route-dot" aria-hidden="true"></span>
    </button>
    <div v-if="open" class="route-box">
      <StationPrefs
        :call="call"
        :paths="paths"
        :fallback-path="fallbackPath"
        :rf-only="rfOnly"
        :suggested="suggested"
        @path="(c, p) => emit('path', c, p)"
        @clear-path="emit('clearPath', $event)"
        @set-rf-only="(c, on) => emit('setRfOnly', c, on)"
      />
    </div>
  </div>
</template>
