<script setup lang="ts">
// The page before the page: it asks the daemon whether this device is let in. This computer always is; a device on the network is shown the key screen until the right key is typed. Only then is the page itself
// (App) mounted, so that it opens its socket with the session the key bought.
import { onMounted, ref } from "vue";
import App from "@/App.vue";
import KeyScreen from "@/components/KeyScreen.vue";
import { probe } from "@/lib/access";

const state = ref<"checking" | "open" | "locked">("checking");

onMounted(async () => {
  state.value = await probe();
});
</script>

<template>
  <KeyScreen v-if="state === 'locked'" @opened="state = 'open'" />
  <App v-else-if="state === 'open'" />
</template>
