<script setup lang="ts">
// The "Radio only" tickbox of a station: messages to it get RFONLY at the end of the path (alone on a
// radio that carries no path), which iGates do not put on the internet. Saved when changed. The
// email gateway has none.
import { t } from "@/i18n";
import { isGateway } from "@/lib/messages";

defineProps<{ call: string; rfOnly: ReadonlySet<string> }>();
const emit = defineEmits<{ set: [call: string, on: boolean] }>();
</script>

<template>
  <label v-if="!isGateway(call)" class="check rfonly">
    <input
      type="checkbox"
      :checked="rfOnly.has(call)"
      @change="emit('set', call, ($event.target as HTMLInputElement).checked)"
    />
    {{ t("route.rf_only") }}
  </label>
</template>
