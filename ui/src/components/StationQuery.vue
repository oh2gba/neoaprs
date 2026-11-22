<script setup lang="ts">
// Directed query box and Ask button for a station panel. The text must match the daemon's rule
// (lib/query.ts): "?" followed by printable ASCII without | ~ {, at most 67 characters. A
// breaking text marks the box and turns Ask off; the reason is only in the title, so no line
// appears and disappears. Ask or Enter sends it upper-cased and empties the box. With RX only,
// or while the radio is not connected (`offline`), Ask is off; the box stays editable.
import { computed, ref } from "vue";
import { useReceiveOnly } from "@/composables/useReceiveOnly";
import { t } from "@/i18n";
import { rxOnlyReason } from "@/lib/compose";
import { customQuery, QUERY_MAX } from "@/lib/query";

const props = withDefaults(defineProps<{ call: string; offline?: string }>(), { offline: undefined });
const emit = defineEmits<{ ask: [text: string] }>();
const rxOnly = useReceiveOnly();

const text = ref("");
const checked = computed(() => customQuery(text.value));
/** Something was typed and it is not a query. An empty box is not wrong. */
const wrong = computed(() => text.value.trim() !== "" && "problem" in checked.value);
const title = computed(() => {
  if (rxOnly.value) return rxOnlyReason();
  const found = checked.value;
  return wrong.value && "problem" in found
    ? t(`station.query.problem.${found.problem}`, { max: QUERY_MAX })
    : t("station.query.title");
});

/** Why Ask is off besides an invalid text: RX only or the radio not connected. */
const blocked = computed(() => (rxOnly.value ? rxOnlyReason() : props.offline));

function submit(): void {
  const found = checked.value;
  if (blocked.value !== undefined || !("text" in found)) return;
  emit("ask", found.text);
  text.value = "";
}
</script>

<template>
  <form class="stationpanel-query" @submit.prevent="submit">
    <input
      v-model="text"
      class="input mono"
      :class="{ invalid: wrong }"
      type="text"
      :maxlength="QUERY_MAX"
      :placeholder="t('station.query.placeholder')"
      :title="title"
      :aria-label="t('station.query.label', { call: props.call })"
      :aria-invalid="wrong"
      :disabled="rxOnly"
      autocomplete="off"
      spellcheck="false"
      data-query="text"
    />
    <button
      type="submit"
      class="btn"
      :disabled="blocked !== undefined || !('text' in checked)"
      :title="blocked ?? title"
      data-query="ask"
    >
      {{ t("station.query.ask") }}
    </button>
  </form>
</template>
