<script setup lang="ts">
// Asks the daemon whether this device may enter and shows the key screen until the right key is
// typed; only then is App mounted. A key in the address (`#key=...`) is taken out of the address
// and sent first, so that a phone opened from the settings code needs no key screen.
import { onMounted, ref } from "vue";
import App from "@/App.vue";
import KeyScreen from "@/components/KeyScreen.vue";
import { login, probe, takeKey } from "@/lib/access";

const state = ref<"checking" | "open" | "locked">("checking");

onMounted(async () => {
  const key = takeKey();
  let now = await probe();
  if (now === "locked" && key !== "" && (await login(key)) === "") now = "open";
  state.value = now;
});
</script>

<template>
  <KeyScreen v-if="state === 'locked'" @opened="state = 'open'" />
  <App v-else-if="state === 'open'" />
</template>
