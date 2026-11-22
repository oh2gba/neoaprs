<script setup lang="ts">
// A level as a bar with its good band and the number beside it, in a fixed room; dimmed (`held`)
// while the radio transmits, when the level shown is the last one received. Feeds:
// HfLevelBar.vue (dBFS) and SoundCardLevel.vue (Direwolf's scale). The feed's (i) goes in the
// slot, and the capture-level slider (or its empty room) in the slot `control` before the bar.
defineProps<{
  id: string;
  label: string;
  percent: number;
  zone: string;
  good: readonly [number, number];
  held: boolean;
  value: string;
}>();
</script>

<template>
  <div class="field">
    <label :for="id">{{ label }}</label>
    <div class="field-control scope-level">
      <slot name="control" />
      <div
        :id="id"
        class="levelbar"
        :class="{ held }"
        role="meter"
        :aria-label="label"
        aria-valuemin="0"
        aria-valuemax="100"
        :aria-valuenow="Math.round(percent)"
        :aria-valuetext="value"
      >
        <span class="levelgood" :style="{ left: `${good[0]}%`, width: `${good[1] - good[0]}%` }"></span>
        <span class="levelfill" :class="zone" :style="{ width: `${percent}%` }"></span>
      </div>
      <output class="mono levelvalue">{{ value }}</output>
      <slot />
    </div>
  </div>
</template>

<style scoped>
.scope-level {
  display: flex;
  align-items: center;
  gap: 8px;
}
.levelbar {
  position: relative;
  flex: 1 1 auto;
  min-width: 60px;
  height: 10px;
  overflow: hidden;
  background: var(--input-bg);
  border: 1px solid var(--border);
  border-radius: 5px;
}
.levelbar.held {
  opacity: 0.45;
}
.levelgood {
  position: absolute;
  top: 0;
  bottom: 0;
  background: var(--level-band);
}
.levelfill {
  position: absolute;
  top: 0;
  bottom: 0;
  left: 0;
  transition: width 0.2s linear;
}
.levelfill.low {
  background: var(--level-low);
}
.levelfill.good {
  background: var(--level-good);
}
.levelfill.high {
  background: var(--level-high);
}
.levelfill.clip {
  background: var(--level-clip);
}
.levelvalue {
  flex: 0 0 auto;
  min-width: 9ch;
  white-space: nowrap;
  text-align: right;
}
@media (prefers-reduced-motion: reduce) {
  .levelfill {
    transition: none;
  }
}
</style>
