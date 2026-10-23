<script setup lang="ts">
// The tickbox "RF only" of a station: everything sent to it goes with RFONLY at the end of its path, which iGates do not put on the internet. It is saved when it is ticked or cleared. The email
// gateway is on the internet, so it has none.
import { isGateway } from "@/lib/messages";

defineProps<{ call: string; rfOnly: ReadonlySet<string> }>();
const emit = defineEmits<{ set: [call: string, on: boolean] }>();
</script>

<template>
  <label v-if="!isGateway(call)" class="check rfonly" title="iGates do not put these messages on the internet">
    <input type="checkbox" :checked="rfOnly.has(call)" @change="emit('set', call, ($event.target as HTMLInputElement).checked)" />
    RF only
  </label>
</template>
