<script setup lang="ts">
// The page before the page: it asks the daemon whether this device is let in. This computer always is; a device on the network is shown the key screen until the right key is typed. Only then is the page itself
// (App) mounted, so that it opens its socket with the session the key bought. A phone that came by the code of Settings, Web page brings the key in the address (`#key=...`): it is taken out of the address first,
// and sent for this device if the daemon asks for one, so the page opens with no key screen; a key that does not work leaves the key screen as it always is, empty, to type the key in.
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
