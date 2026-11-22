<script setup lang="ts">
// The two faces of a button that asks twice ("Forget", then "sure?"). Both are rendered and the
// hidden one keeps the width and height (`.twowords`, styles/tables.css), so the first press
// moves nothing. `second` selects the face shown, for screen readers too.
defineProps<{ second: boolean }>();
</script>

<template>
  <span class="twowords"
    ><span :class="{ 'twowords-off': second }" :aria-hidden="second"><slot name="first"></slot></span
    ><span :class="{ 'twowords-off': !second }" :aria-hidden="!second"><slot name="second"></slot></span
  ></span>
</template>
