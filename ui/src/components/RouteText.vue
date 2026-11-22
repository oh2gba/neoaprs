<script setup lang="ts">
// A route in words: the line may break between words, never inside a callsign.
import { computed } from "vue";

const props = defineProps<{ text: string }>();
const words = computed(() => props.text.split(" ").filter((word) => word !== ""));
</script>

<template>
  <span class="route"
    ><template v-for="(word, index) in words" :key="index"
      ><span class="nowrap">{{ word }}</span
      >{{ index < words.length - 1 ? " " : "" }}</template
    ></span
  >
</template>
