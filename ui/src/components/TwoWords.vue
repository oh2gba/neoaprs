<script setup lang="ts">
// The two faces of a button that asks twice ("Forget", then "sure?"; a trash can, then "sure?"): both are in the page, in one place, the one not shown hidden, so that the button is as wide and as high as the larger and the first press moves nothing (`.twowords`, styles/tables.css).
// `second` says which is shown: the first face until the first press, the second after it, for a screen reader as for the eye (the hidden face is not read).
defineProps<{ second: boolean }>();
</script>

<template>
  <span class="twowords"
    ><span :class="{ 'twowords-off': second }" :aria-hidden="second"><slot name="first"></slot></span
    ><span :class="{ 'twowords-off': !second }" :aria-hidden="!second"><slot name="second"></slot></span
  ></span>
</template>
