<script setup lang="ts">
// How far the path goes, the two plain controls of the path builder that make its aliases (lib/pathreach.ts): **Hops**, Direct, 1, 2 or 3 in all, one pressed when the path is that many (none for a longer path or one that is no
// path), and **Home digis may take the first hop**, which makes the first alias hop WIDE1-1 (a home, fill-in, digipeater takes it as well as a wide one) and else a wide one: 1 is WIDE1-1 or WIDE2-1, 2 WIDE1-1,WIDE2-1 or WIDE2-2,
// 3 WIDE1-1,WIDE2-2 or WIDE3-3. A choice keeps the digipeaters named at the start of the path as far as they go, and the hops left are wide ones after them; Direct is none at all. The tick follows a path that starts with an alias
// and changes it at once; it is off, with the reason in its title, while the first hop is a digipeater named (it is that one) or the path is none of the choices. Each choice's hover title is the path it makes. What is put in
// the slot (As its packets come) sits beside the choices.
import { computed, useId } from "vue";
import { t } from "@/i18n";
import { pathOf } from "@/lib/pathbuilder";
import { REACHES, reachOf, splitPath, withReach } from "@/lib/pathreach";

const props = defineProps<{ hops: readonly string[]; home: boolean }>();
const emit = defineEmits<{ set: [hops: string[]]; home: [on: boolean] }>();

const id = useId();
const pressed = computed(() => reachOf(props.hops));
const named = computed(() => splitPath(props.hops).lead[0] ?? null);
/** Why the tick is off: the first hop is named, or the path is none of the choices; "" while it is on. */
const homeOff = computed(() =>
  named.value !== null ? t("pathbuilder.home_named", { call: named.value }) : pressed.value === null ? t("pathbuilder.home_choose") : "",
);
const choiceTitle = (count: number): string =>
  count === 0 ? t("pathbuilder.reach_direct") : t("pathbuilder.reach_title", { n: count, path: pathOf(withReach(props.hops, count, props.home)) });

function tick(event: Event): void {
  if (!(event.target instanceof HTMLInputElement)) return;
  const on = event.target.checked;
  emit("home", on);
  if (pressed.value !== null && pressed.value > 0) emit("set", withReach(props.hops, pressed.value, on));
}
</script>

<template>
  <div class="pathbuild-reach">
    <span :id="`${id}-hops`" class="pathbuild-reach-label">{{ t("pathbuilder.hops_label") }}</span>
    <div class="pathbuild-seg" role="group" :aria-labelledby="`${id}-hops`">
      <button
        v-for="count in REACHES"
        :key="count"
        type="button"
        class="btn"
        :class="{ primary: pressed === count }"
        :aria-pressed="pressed === count"
        :title="choiceTitle(count)"
        @click="emit('set', withReach(hops, count, home))"
      >
        {{ count === 0 ? t("pathbuilder.direct") : count }}
      </button>
    </div>
    <slot></slot>
  </div>
  <label class="check pathbuild-home" :title="homeOff || t('pathbuilder.home_title')">
    <input type="checkbox" :checked="home && named === null" :disabled="homeOff !== ''" @change="tick" />
    {{ t("pathbuilder.home") }}
  </label>
</template>
