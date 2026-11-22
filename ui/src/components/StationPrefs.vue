<script setup lang="ts">
// How messages to one station are sent (Route of a conversation and of the station panel): the
// radio (when more than one is on; "Automatic" names the radio it gives now), then the path and
// RF only. Path and RF only are greyed, value kept, while the radio in force carries no path
// (`pathless`); RF only stays live when messages go through a gateway (`reply`). For an unknown
// call the radio row is shown greyed (`fixed`) so nothing moves when the station is heard.
// `heard` is the path last heard to reach the station (null: none).
import { useId } from "vue";
import StationPath from "@/components/StationPath.vue";
import StationRfOnly from "@/components/StationRfOnly.vue";
import { t } from "@/i18n";
import type { PageRadio, RadioId } from "@/lib/radios";

withDefaults(
  defineProps<{
    call: string;
    paths: ReadonlyMap<string, string>;
    fallbackPath: string;
    rfOnly?: ReadonlySet<string>;
    heard?: string | null;
    /** the radios to choose among; none (or one) for no radio row */
    radios?: readonly PageRadio[];
    /** the radio chosen; null: automatic */
    choice?: RadioId | null;
    /** the radio "Automatic" gives now; null when it is not known */
    auto?: string | null;
    /** the radio cannot be chosen yet (unknown call); the row is greyed so nothing moves later */
    fixed?: boolean;
    /** the path and RF only are offered (a radio that is on may carry a path) */
    pathShown?: boolean;
    pathless?: string;
    /** the reply path through a gateway on the radio in force with no path; empty for none */
    reply?: string;
  }>(),
  {
    rfOnly: () => new Set<string>(),
    heard: null,
    radios: () => [],
    choice: null,
    auto: null,
    fixed: false,
    pathShown: true,
    pathless: undefined,
    reply: "",
  },
);
const emit = defineEmits<{
  path: [call: string, path: string];
  clearPath: [call: string];
  setRfOnly: [call: string, on: boolean];
  radio: [call: string, radio: RadioId | null];
}>();
const id = useId();

/**
 * The radio picked in the list: its id, or null for "Automatic". The list reverts to the radio
 * in force until the station's row confirms the change.
 */
function picked(event: Event, call: string, choice: RadioId | null): void {
  const list = event.target as HTMLSelectElement;
  emit("radio", call, list.value === "" ? null : Number(list.value));
  list.value = choice === null ? "" : String(choice);
}
</script>

<template>
  <div class="prefs">
    <div v-if="radios.length > 1" class="pathbox route-radio" :class="{ disabled: fixed }">
      <label :for="id" class="path-label">{{ t("radio.choice") }}</label>
      <select :id="id" class="input route-radio-pick" :value="choice === null ? '' : String(choice)" :disabled="fixed" @change="picked($event, call, choice)">
        <option value="">{{ auto === null ? t("radio.automatic") : t("route.radio_auto", { name: auto }) }}</option>
        <option v-for="radio in radios" :key="radio.id" :value="String(radio.id)">{{ radio.name }}</option>
      </select>
    </div>
    <StationPath
      v-if="pathShown"
      :call="call"
      :paths="paths"
      :fallback="fallbackPath"
      :heard="heard"
      :pathless="pathless"
      :reply="reply"
      @set="(c, p) => emit('path', c, p)"
      @clear="emit('clearPath', $event)"
    >
      <StationRfOnly :call="call" :rf-only="rfOnly" :pathless="reply === '' ? pathless : undefined" @set="(c, on) => emit('setRfOnly', c, on)" />
    </StationPath>
  </div>
</template>
