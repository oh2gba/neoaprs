<script setup lang="ts">
// Send on as a form row (useSendOn): the label, a tick per radio by name (the last one ticked is
// greyed) and the daemon's refusal under them. One row serves the Beacon, Status, Ask around, Local
// info, object form and Post box, each with its own `id`.
import { t } from "@/i18n";
import type { SendOnTick } from "@/lib/beaconstatus";
import { fieldId } from "@/lib/radios";

defineProps<{ id: string; ticks: readonly SendOnTick[]; error: string }>();
const emit = defineEmits<{ tick: [key: string, on: boolean] }>();

function changed(key: string, event: Event): void {
  if (event.target instanceof HTMLInputElement) emit("tick", key, event.target.checked);
}
</script>

<template>
  <div class="field" :class="{ invalid: error !== '' }" role="group" :aria-labelledby="id">
    <span :id="id" class="field-label">{{ t("radio.send_on") }}</span>
    <div class="field-control toolbar-checks">
      <label v-for="one in ticks" :key="one.key" class="check">
        <input
          :id="`set-${fieldId(one.key)}`"
          type="checkbox"
          :checked="one.on"
          :disabled="one.last"
          @change="changed(one.key, $event)"
        />{{ one.name }}
      </label>
    </div>
    <p v-if="error" class="field-error" role="alert">{{ error }}</p>
  </div>
</template>
