<script setup lang="ts">
// The QR code of `link` (the page address with the access key after `#`), drawn as one path of dark
// modules on a white field in both themes. The box has a fixed size; the viewBox is the code's size
// in modules. It is an image named by `labelledby`; the address and key are not printed or read
// aloud.
import { computed } from "vue";
import { qrMatrix, qrPath } from "@/lib/qr";

const props = defineProps<{ link: string; labelledby: string }>();
const code = computed(() => qrPath(qrMatrix(props.link)));
</script>

<template>
  <svg
    class="phonecode"
    role="img"
    :aria-labelledby="labelledby"
    :viewBox="`0 0 ${code.size} ${code.size}`"
    shape-rendering="crispEdges"
  >
    <rect class="phonecode-field" :width="code.size" :height="code.size" />
    <path class="phonecode-dark" :d="code.d" />
  </svg>
</template>
