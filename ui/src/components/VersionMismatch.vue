<script setup lang="ts">
// Shown instead of the page when the daemon speaks another protocol or serves another build
// (lib/reload.ts): one sentence and a button that reloads. The page's socket stays closed.
import { t } from "@/i18n";
import type { Mismatch } from "@/lib/reload";

defineProps<{ mismatch: Mismatch }>();
// lib/reload.ts keeps its guard: a mismatch that persists after this load is reported at once.
const reload = (): void => location.reload();
</script>

<template>
  <main class="mismatch" role="alert">
    <p>{{ t("mismatch.notice", { page: mismatch.page, neoaprs: mismatch.neoaprs }) }}</p>
    <button class="btn primary" type="button" @click="reload">{{ t("mismatch.reload") }}</button>
  </main>
</template>
