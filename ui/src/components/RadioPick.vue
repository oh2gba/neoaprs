<script setup lang="ts">
// The choice of a radio beside a button that asks (Local info's Ask, Ask around: plan rule 3.6), one look for both: the radios that are on by their names, the main radio first (useRadios `choose`). Its parent shows it
// only while several radios are on.
import { t } from "@/i18n";
import type { PageRadio, RadioId } from "@/lib/radios";

defineProps<{ radio: RadioId | null; choices: readonly PageRadio[] }>();
const emit = defineEmits<{ pick: [radio: RadioId] }>();
</script>

<template>
  <select class="input" :value="radio" :aria-label="t('radio.choice')" @change="emit('pick', Number(($event.target as HTMLSelectElement).value))">
    <option v-for="choice in choices" :key="choice.id" :value="choice.id">{{ choice.name }}</option>
  </select>
</template>
