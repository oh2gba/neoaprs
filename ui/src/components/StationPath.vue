<script setup lang="ts">
// The path a message to a station, and the ack of one from it, goes by way of: the digipeaters, separated by commas. Left empty the choice is automatic and the line under the field says what it is: the first two attempts of a
// message go by the path that has lately been heard to reach the station (`heard`, the daemon's), the others by the beacon's path (`fallback`). A path typed is the station's own and is used for every attempt ("Your path:"); the word
// DIRECT is an own path with no digipeaters. It is saved when the field is changed and left, or Enter is pressed (the browser's change event), and the x (or an empty field) gives the choice back to the automatic one. What is put
// in the slot (the RF only tickbox) sits beside it.
import { computed, ref, useId, watch } from "vue";
import { t } from "@/i18n";
import { DIRECT, parsePathSetting } from "@/lib/calls";
import { effectivePath } from "@/lib/messages";
import { LIMITS } from "@/protocol/lists";

const props = withDefaults(defineProps<{ call: string; paths: ReadonlyMap<string, string>; fallback: string; heard?: string | null }>(), {
  heard: null,
});
const emit = defineEmits<{ set: [call: string, path: string]; clear: [call: string] }>();

const id = useId();
const effective = computed(() => effectivePath(props.paths, props.fallback, props.call));
/** The station's own path as the field writes it: empty when it has none, DIRECT for one with no digipeaters. */
const own = computed(() => (!effective.value.own ? "" : effective.value.text === "" ? DIRECT : effective.value.text));
const draft = ref(own.value);
const setting = computed(() => parsePathSetting(draft.value));

watch([() => props.call, own], () => (draft.value = own.value));

/** The one line under the field: what the messages go by. */
const line = computed(() => {
  const word = (path: string): string => (path === "" ? t("route.direct") : path);
  if (effective.value.own) return t("route.own", { path: word(effective.value.text) });
  if (props.heard === null || props.heard === props.fallback) return t("route.auto", { path: word(props.fallback) });
  if (props.heard === "") return t("route.auto_direct", { path: word(props.fallback) });
  return t("route.auto_via", { heard: props.heard, path: word(props.fallback) });
});

function save(): void {
  const found = setting.value;
  if (found === null) return;
  if (found.kind === "auto") {
    draft.value = "";
    if (effective.value.own) emit("clear", props.call);
    return;
  }
  const text = found.kind === "direct" ? DIRECT : found.calls.join(",");
  draft.value = text;
  if (text !== own.value) emit("set", props.call, text);
}
</script>

<template>
  <div class="pathbox">
    <label :for="id" class="path-label">{{ t("route.path") }}</label>
    <input
      :id="id"
      v-model="draft"
      class="input mono grow"
      :class="{ invalid: setting === null }"
      type="text"
      :placeholder="t('route.automatic')"
      :title="setting === null ? t('route.calls_hint', { max: LIMITS.path.maxCalls }) : undefined"
      autocomplete="off"
      spellcheck="false"
      @change="save"
    />
    <button
      v-if="effective.own"
      type="button"
      class="iconbtn use-default"
      :aria-label="t('route.use_auto')"
      :title="t('route.use_auto')"
      @click="emit('clear', call)"
    >
      ×
    </button>
    <slot />
    <span class="path-line muted">{{ line }}</span>
  </div>
</template>
