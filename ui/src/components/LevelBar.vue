<script setup lang="ts">
// A level as a bar with its good band and the number beside it, in a room that is kept so that nothing moves when the number changes; dimmed (`held`) while the radio transmits, when the level shown is the last one
// received. Its feeds are the HF radio's scope (components/HfLevelBar.vue, in dBFS) and a Sound card radio's modem (components/SoundCardLevel.vue, on Direwolf's own scale); the (i) of a feed goes in the slot, and the
// slider of the sound card's own capture level (or its empty room, where the card has none), in the slot `control` before the bar (one row: the slider sets, the bar shows; the slider is no higher than the (i), and nothing in the row moves while its value changes).
defineProps<{ id: string; label: string; percent: number; zone: string; good: readonly [number, number]; held: boolean; value: string }>();
</script>

<template>
  <div class="field">
    <label :for="id">{{ label }}</label>
    <div class="field-control scope-level">
      <slot name="control" />
      <div :id="id" class="levelbar" :class="{ held }" role="meter" :aria-label="label">
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
  text-align: right;
}
@media (prefers-reduced-motion: reduce) {
  .levelfill {
    transition: none;
  }
}
</style>
