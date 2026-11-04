<script setup lang="ts">
// The HF radio's scope: a distant station sends (waves), and the waterfall of the audio shows its frame as a block in the marked band at the top, the newest rows, over the faint specks of the noise, with the receive level under it as a bar in the
// good range.
import { CALLS } from "@/help/calls";
import { waves } from "@/help/draw";
import HelpFrame from "@/help/HelpFrame.vue";
import HelpStation from "@/help/HelpStation.vue";

const noise = "M30 64h6M52 86h5M70 72h4M88 94h6M128 90h4M156 96h5M188 66h6M206 84h4M226 74h5M246 92h6";
const band = "M110 50v52M170 50v52";
</script>

<template>
  <HelpFrame name="scope">
    <HelpStation table="/" code="-" :x="244" :y="18" :size="26" :label="CALLS.other" />
    <path class="hp-flow" :d="waves(228, 18, 180, 2, 8, 5)" />
    <rect class="hp-frame" x="20" y="50" width="240" height="52" rx="3" />
    <path class="hp-dim hp-dash" :d="band" />
    <path class="hp-dim" :d="noise" />
    <rect class="hp-wash" x="110" y="54" width="60" height="24" />
    <rect class="hp-frame" x="20" y="116" width="240" height="14" rx="3" />
    <rect class="hp-ok" x="80" y="116" width="90" height="14" rx="3" />
    <path class="hp-lit" d="M120 112v22" />
  </HelpFrame>
</template>
