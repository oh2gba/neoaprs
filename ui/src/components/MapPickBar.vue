<script setup lang="ts">
// A phone shows the map alone while a place is picked on it (the Beacon tab's and the Objects tab's Pick on the map): this bar over the map says what to do and has Cancel, which ends the picking and brings the tab back.
const emit = defineEmits<{ cancel: [] }>();
</script>

<template>
  <div class="pickbar" role="status">
    <span>Tap the place on the map</span>
    <button type="button" class="btn small" @click="emit('cancel')">Cancel</button>
  </div>
</template>
