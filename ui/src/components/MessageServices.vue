<script setup lang="ts">
// Services, in the head of the conversation list: a ready-made start of a message to a service
// station (lib/services.ts), chosen in the list, and Write. Write opens the conversation with the
// service's addressee and puts the fixed start of the text in the box; the operator completes it
// and sends it as an ordinary message. The choice is remembered by this browser.
import { computed } from "vue";
import { usePersisted } from "@/composables/usePersisted";
import { t } from "@/i18n";
import { SERVICES, serviceGroups, serviceName } from "@/lib/services";

const emit = defineEmits<{ write: [to: string, text: string] }>();

const first = SERVICES[0];
const chosen = usePersisted(
  "messages.service",
  first.id,
  SERVICES.map((service) => service.id),
);
const service = computed(() => SERVICES.find((s) => s.id === chosen.value) ?? first);
const groups = serviceGroups();
/** What Write writes: the addressee and the start of the text. */
const what = computed(() => t("messages.service_title", { to: service.value.to, text: service.value.text.trim() }));
</script>

<template>
  <div class="convlist-services">
    <label for="msg-service">{{ t("messages.services") }}</label>
    <select id="msg-service" v-model="chosen" class="input">
      <template v-for="group in groups" :key="group.group ?? ''">
        <optgroup v-if="group.group !== null" :label="group.group">
          <option v-for="s in group.services" :key="s.id" :value="s.id">{{ serviceName(s) }}</option>
        </optgroup>
        <template v-else>
          <option v-for="s in group.services" :key="s.id" :value="s.id">{{ serviceName(s) }}</option>
        </template>
      </template>
    </select>
    <button type="button" class="btn" :title="what" @click="emit('write', service.to, service.text)">
      {{ t("messages.service_write") }}
    </button>
  </div>
</template>
