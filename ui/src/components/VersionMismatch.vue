<script setup lang="ts">
// What the page shows instead of itself when the daemon is of another protocol or serves another build of the page (lib/reload.ts): one sentence, in the page's language, and a button that loads the page again. The page's socket stays closed meanwhile.
import { t } from "@/i18n";
import type { Mismatch } from "@/lib/reload";

defineProps<{ mismatch: Mismatch }>();
const reload = (): void => location.reload(); // (the guard of lib/reload.ts stays: a mismatch that is still there after this load is told at once, and a daemon that changed meanwhile gets its own load)
</script>

<template>
  <main class="mismatch" role="alert">
    <p>{{ t("mismatch.notice", { page: mismatch.page, neoaprs: mismatch.neoaprs }) }}</p>
    <button class="btn primary" type="button" @click="reload">{{ t("mismatch.reload") }}</button>
  </main>
</template>
