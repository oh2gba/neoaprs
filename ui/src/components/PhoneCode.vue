<script setup lang="ts">
// The code a phone's camera opens the page from (Settings, Web page, under the access key): the QR code of `link`, the page's address with the access key after `#`, drawn as one path of dark modules on a white
// field in both themes, so that every camera reads it. Its box is a square of one size; the viewBox is the code's own size in modules, so a longer address makes the modules smaller and never the box bigger.
// It is an image named by the row's label (`labelledby`): the address and the key are neither printed nor read aloud.
import { computed } from "vue";
import { qrMatrix, qrPath } from "@/lib/qr";

const props = defineProps<{ link: string; labelledby: string }>();
const code = computed(() => qrPath(qrMatrix(props.link)));
</script>

<template>
  <svg class="phonecode" role="img" :aria-labelledby="labelledby" :viewBox="`0 0 ${code.size} ${code.size}`" shape-rendering="crispEdges">
    <rect class="phonecode-field" :width="code.size" :height="code.size" />
    <path class="phonecode-dark" :d="code.d" />
  </svg>
</template>
