<script setup lang="ts">
// The tickbox "RF only" of a station: everything sent to it goes with RFONLY at the end of its path, which iGates do not put on the internet. It is saved when it is ticked or cleared. The email
// gateway is on the internet, so it has none. `pathless` greys it, ticked or not, while the radio in force carries no path, and says why on hover.
import { t } from "@/i18n";
import { isGateway } from "@/lib/messages";

withDefaults(defineProps<{ call: string; rfOnly: ReadonlySet<string>; pathless?: string }>(), { pathless: undefined });
const emit = defineEmits<{ set: [call: string, on: boolean] }>();
</script>

<template>
  <label v-if="!isGateway(call)" class="check rfonly" :title="pathless ?? t('route.rf_only_title')">
    <input
      type="checkbox"
      :checked="rfOnly.has(call)"
      :disabled="pathless !== undefined"
      @change="emit('set', call, ($event.target as HTMLInputElement).checked)"
    />
    {{ t("route.rf_only") }}
  </label>
</template>
