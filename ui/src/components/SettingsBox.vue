<script setup lang="ts">
// A box inside a group of the Settings tab, in the style of the group boxes: a fieldset with its legend (`title`; the slot `legend` is what stands after it, an (i)), so that it is plain which device a part of the Notifications group is for ("On the NeoAPRS computer", "In this browser"). Without a title it is only its content.
defineProps<{ title?: string; hover?: string }>();
</script>

<template>
  <fieldset v-if="title" class="subbox">
    <legend :title="hover">
      {{ title }}
      <slot name="legend"></slot>
    </legend>
    <slot></slot>
  </fieldset>
  <slot v-else></slot>
</template>
