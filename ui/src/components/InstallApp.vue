<script setup lang="ts">
// "Install app": shown only where the browser has offered to install the page as an app (composables/useInstall.ts); nothing is there otherwise.
import { useInstall } from "@/composables/useInstall";

const { canInstall, install } = useInstall();
</script>

<template>
  <div v-if="canInstall" class="field">
    <label for="install-app">App</label>
    <div class="field-control">
      <button id="install-app" class="btn" type="button" title="Open NeoAPRS in a window of its own, with an icon" @click="install">Install app</button>
    </div>
  </div>
</template>
