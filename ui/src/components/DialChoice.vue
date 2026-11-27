<script setup lang="ts">
// A dial chosen as the HF tests form and a Mercury radio's box choose it: Frequency, a select of the
// suggested dials and Other, and under it the row of the number alone (`7.0541`, a comma too) with MHz
// USB fixed beside it (lib/skeds.ts dialOfNumber). The number row is always there, so that nothing
// moves: greyed with the chosen dial's number while a dial of the list is chosen, open for typing
// (from empty) once Other is. The parent holds `typed` and `dial` (a dial of the list, or the number
// typed while `typed`); `choose` is a choice of the select (a dial or OTHER_DIAL), `commit` the typed
// number finished on leaving the field or, with `apply`, on Enter. `blank` offers an empty choice
// while the dial is empty; `least` is the lowest number in MHz that is no wrong one. `disabled`
// greys both rows.
import { computed, ref } from "vue";
import { t } from "@/i18n";
import { confirms } from "@/lib/ime";
import { OTHER_DIAL, dialAtLeast, numberOfDial } from "@/lib/skeds";
import type { SkedFrequency } from "@/protocol/protocol";

const props = withDefaults(
  defineProps<{
    id: string;
    dialId: string;
    frequencies: readonly SkedFrequency[];
    typed: boolean;
    dial: string;
    disabled?: boolean;
    apply?: boolean;
    blank?: boolean;
    least?: number;
  }>(),
  { disabled: false, apply: false, blank: false, least: 0 },
);
const emit = defineEmits<{ choose: [value: string]; "update:dial": [text: string]; commit: [] }>();

const choice = computed(() => (props.typed ? OTHER_DIAL : props.dial));
const typedWrong = computed(
  () => props.typed && props.dial.trim() !== "" && dialAtLeast(props.dial, props.least) === null,
);
/** What the number field shows: the typed text, else the number of the chosen dial. */
const number = computed(() => (props.typed ? props.dial : numberOfDial(props.dial)));
/** The row of the select, for a parent that asks for the dials when it comes on show. */
const row = ref<HTMLElement | null>(null);
defineExpose({ row });

function enter(event: KeyboardEvent): void {
  if (!props.apply || !confirms(event)) return;
  event.preventDefault();
  emit("commit");
}
</script>

<template>
  <div ref="row" class="field" :class="{ disabled }">
    <label :for="id">{{ t("skeds.frequency") }}</label>
    <div class="field-control">
      <select
        :id="id"
        class="input"
        :value="choice"
        :disabled="disabled"
        @change="emit('choose', ($event.target as HTMLSelectElement).value)"
      >
        <option v-if="blank && choice === ''" value=""></option>
        <option v-for="f in frequencies" :key="f.band" :value="f.dial">{{ `${f.dial} (${f.band})` }}</option>
        <option :value="OTHER_DIAL">{{ t("skeds.frequency_other") }}</option>
      </select>
    </div>
  </div>
  <div class="field" :class="{ invalid: typedWrong, disabled: disabled || !typed }">
    <label :for="dialId">{{ t("skeds.dial") }}</label>
    <div class="field-control">
      <input
        :id="dialId"
        :value="number"
        class="input mono"
        :class="{ invalid: typedWrong }"
        type="text"
        inputmode="decimal"
        autocomplete="off"
        spellcheck="false"
        :disabled="disabled || !typed"
        @input="emit('update:dial', ($event.target as HTMLInputElement).value)"
        @blur="emit('commit')"
        @keydown.enter="enter"
      />
      <span class="unit muted">MHz USB</span>
    </div>
  </div>
</template>
