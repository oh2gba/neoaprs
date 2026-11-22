<script setup lang="ts">
// Path field for messages to one station. Empty means automatic: the first two attempts use the
// path last heard to reach the station (`heard`), the rest use the beacon path (`fallback`).
// DIRECT is an own path with no digipeaters. Saved on change or Enter; the clear button
// restores the automatic choice. `pathless` greys the row while the radio in force carries no
// path; the line then shows the gateway reply path (`reply`) or direct.
import { computed, ref, useId, watch } from "vue";
import PathBuilder from "@/components/PathBuilder.vue";
import { t } from "@/i18n";
import { DIRECT, parsePathSetting } from "@/lib/calls";
import { effectivePath } from "@/lib/messages";
import { LIMITS } from "@/protocol/lists";

const props = withDefaults(
  defineProps<{ call: string; paths: ReadonlyMap<string, string>; fallback: string; heard?: string | null; pathless?: string; reply?: string }>(),
  {
    heard: null,
    pathless: undefined,
    reply: "",
  },
);
const emit = defineEmits<{ set: [call: string, path: string]; clear: [call: string] }>();

const id = useId();
const effective = computed(() => effectivePath(props.paths, props.fallback, props.call));
/** The station's own path as the field writes it; DIRECT when it has no digipeaters. */
const own = computed(() => (!effective.value.own ? "" : effective.value.text === "" ? DIRECT : effective.value.text));
const draft = ref(own.value);
const setting = computed(() => parsePathSetting(draft.value));

watch([() => props.call, own], () => (draft.value = own.value));

/** The one line under the field: what the messages go by. */
const line = computed(() => {
  const word = (path: string): string => (path === "" ? t("route.direct") : path);
  if (props.pathless !== undefined) return t("route.auto", { path: props.reply === "" ? t("route.direct") : t("route.via", { hops: props.reply }) });
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

/** Put the built path into the field and save it. */
function build(path: string): void {
  draft.value = path;
  save();
}
</script>

<template>
  <div class="pathbox" :class="{ disabled: pathless !== undefined }">
    <label :for="id" class="path-label">{{ t("route.path") }}</label>
    <input
      :id="id"
      v-model="draft"
      class="input mono grow"
      :class="{ invalid: setting === null }"
      type="text"
      :placeholder="t('route.automatic')"
      :title="pathless ?? (setting === null ? t('route.calls_hint', { max: LIMITS.path.maxCalls }) : undefined)"
      :disabled="pathless !== undefined"
      autocomplete="off"
      spellcheck="false"
      @change="save"
    />
    <PathBuilder :value="draft" :usual="effective.text" :station="call" :disabled="pathless !== undefined" :why="pathless" @use="build" />
    <button
      v-if="effective.own"
      type="button"
      class="xbtn use-default"
      :aria-label="t('route.use_auto')"
      :title="t('route.use_auto')"
      :disabled="pathless !== undefined"
      @click="emit('clear', call)"
    >
      ×
    </button>
    <slot />
    <span class="path-line muted">{{ line }}</span>
  </div>
</template>
