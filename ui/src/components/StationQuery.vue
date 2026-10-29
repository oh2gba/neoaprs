<script setup lang="ts">
// The operator's own directed query in the station panel of the Stations tab, under its query buttons: a box and Ask, in one line. The text is held to the daemon's rule (lib/query.ts: "?" and something after it, printable
// ASCII without | ~ {, at most 67 characters, which the box takes no more of); while it breaks it the box has the red edge of every field that is wrong and Ask is off, and why is said only in the box's hover title, so that no
// line comes and goes under it. Ask (or Enter) sends it upper-cased (`ask`) and empties the box. The hover title of the box names the other directed queries of the specification. With RX only both are off.
import { computed, ref } from "vue";
import { useReceiveOnly } from "@/composables/useReceiveOnly";
import { t } from "@/i18n";
import { rxOnlyReason } from "@/lib/compose";
import { customQuery, QUERY_MAX } from "@/lib/query";

const props = defineProps<{ call: string }>();
const emit = defineEmits<{ ask: [text: string] }>();
const rxOnly = useReceiveOnly();

const text = ref("");
const checked = computed(() => customQuery(text.value));
/** Something was typed and it is no query: the box is marked. An empty box is not wrong, only not ready. */
const wrong = computed(() => text.value.trim() !== "" && "problem" in checked.value);
const title = computed(() => {
  if (rxOnly.value) return rxOnlyReason();
  const found = checked.value;
  return wrong.value && "problem" in found ? t(`station.query.problem.${found.problem}`, { max: QUERY_MAX }) : t("station.query.title");
});

function submit(): void {
  const found = checked.value;
  if (rxOnly.value || !("text" in found)) return;
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
    <button type="submit" class="btn" :disabled="rxOnly || !('text' in checked)" :title="title" data-query="ask">{{ t("station.query.ask") }}</button>
  </form>
</template>
