<script setup lang="ts">
// What a device on the network sees before it is let in: one field for the access key and one button. A wrong key is told under the field; the right one makes the daemon give this browser a session, and the page opens.
import { onMounted, ref } from "vue";
import { login } from "@/lib/access";

const emit = defineEmits<{ opened: [] }>();
const key = ref("");
const error = ref("");
const busy = ref(false);
const field = ref<HTMLInputElement | null>(null);

onMounted(() => field.value?.focus());

async function submit(): Promise<void> {
  if (busy.value || key.value.trim() === "") return;
  busy.value = true;
  error.value = await login(key.value);
  busy.value = false;
  if (error.value === "") emit("opened");
}
</script>

<template>
  <form class="keyscreen" novalidate @submit.prevent="submit">
    <input
      id="access-key"
      ref="field"
      v-model="key"
      class="input"
      type="text"
      name="key"
      autocomplete="off"
      autocapitalize="none"
      spellcheck="false"
      placeholder="xxxx-xxxx-xxxx"
      aria-label="Access key"
      :aria-invalid="error !== ''"
      @input="error = ''"
    />
    <button class="btn primary" type="submit" :disabled="busy || key.trim() === ''">Open</button>
    <p v-if="error" class="field-error" role="alert">{{ error }}</p>
  </form>
</template>
