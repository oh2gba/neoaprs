<script setup lang="ts">
// The "RF only" tickbox of a station: messages to it get RFONLY at the end of the path, which
// iGates do not put on the internet. Saved when changed. The email gateway has none. `pathless`
// greys it while the radio in force carries no path.
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
