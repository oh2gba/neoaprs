<script setup lang="ts">
// A route in words ("via OH2RCH-2", "via a repeater → OH2RCH-2"): the line may break between its words and never inside a callsign.
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
