<script setup lang="ts">
// The logs for support: a file of lines (the log) that goes, attached, in a mail.
import { arrow } from "@/help/draw";
import HelpFrame from "@/help/HelpFrame.vue";
</script>

<template>
  <HelpFrame name="logs">
    <path class="hp-solid" d="M46 22h50l22 22v82H46z" />
    <path class="hp-solid" d="M96 22v22h22" />
    <path class="hp-dim" d="M58 62h46M58 78h46M58 94h30M58 110h40" />
    <path class="hp-flow" :d="arrow(130, 76, 160, 76)" />
    <rect class="hp-card hp-lit" x="172" y="46" width="76" height="52" rx="5" />
    <path class="hp-lit" d="M172 50l38 26 38-26" />
  </HelpFrame>
</template>
