<script setup lang="ts">
// One symbol as a button that chooses it: the picture and its name, pressed (`active`) for the one in use. The grids of the symbol picker and of the setup guide give it their class, which is the look.
import SymbolIcon from "@/components/SymbolIcon.vue";

defineProps<{ table: string; code: string; name: string; active: boolean }>();
defineEmits<{ pick: [] }>();
</script>

<template>
  <button type="button" :class="{ active }" :aria-pressed="active" @click="$emit('pick')">
    <SymbolIcon :table="table" :code="code" :size="32" />
    <span>{{ name }}</span>
  </button>
</template>
