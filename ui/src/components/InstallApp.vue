<script setup lang="ts">
// "Install app": shown only where the browser has offered to install the page as an app (composables/useInstall.ts); nothing is there otherwise.
import { t } from "@/i18n";
import { useInstall } from "@/composables/useInstall";

const { canInstall, install } = useInstall();
</script>

<template>
  <div v-if="canInstall" class="field">
    <label for="install-app">{{ t("help.install.label") }}</label>
    <div class="field-control">
      <button id="install-app" class="btn" type="button" :title="t('help.install.title')" @click="install">{{ t("help.install.button") }}</button>
    </div>
  </div>
</template>
