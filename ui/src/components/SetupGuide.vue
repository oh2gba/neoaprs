<script setup lang="ts">
// The first-run guide: a compact panel over the map with five steps (Call, Position, Symbol, Radio, Map), a step indicator that goes back to any step and forward to the next one that can be reached, Back, and Next (Finish on the last).
// It opens by itself when the daemon has no call, and again from the Setup button of the Settings tab and from "no call set" in the header; Escape and the cross close it, and what was typed is still there when it is opened again.
// The state is `useSetupGuide`'s; this is the frame, and a step is a component of its own. On a narrow page "On the map" folds the panel to its head so that the map can be clicked.
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import IconButton from "@/components/IconButton.vue";
import SetupCall from "@/components/SetupCall.vue";
import SetupMap from "@/components/SetupMap.vue";
import SetupPosition from "@/components/SetupPosition.vue";
import SetupRadio from "@/components/SetupRadio.vue";
import SetupSymbol from "@/components/SetupSymbol.vue";
import { useDaemonContext } from "@/composables/useDaemonContext";
import { LAST_STEP, STEP_TITLES } from "@/lib/setup";

const { guide } = useDaemonContext();
const root = ref<HTMLElement | null>(null);

function onKey(event: KeyboardEvent): void {
  if (event.key === "Escape" && guide.open && !event.defaultPrevented) guide.close();
}
onMounted(() => document.addEventListener("keydown", onKey));
onBeforeUnmount(() => document.removeEventListener("keydown", onKey));

/** The first field of the step is ready to type in when the guide opens and when the step changes. */
watch(
  () => [guide.open, guide.step] as const,
  async ([open]) => {
    if (!open) return;
    await nextTick();
    root.value?.querySelector<HTMLElement>(".setup-body input, .setup-body select, .setup-body .setup-symbol")?.focus();
  },
  { flush: "post", immediate: true },
);
</script>

<template>
  <section v-if="guide.open" ref="root" class="setup" :class="{ peeking: guide.peeking }" role="dialog" aria-label="Setup">
    <form novalidate @submit.prevent="guide.next()">
      <header class="setup-head">
        <h2>
          Setup<span class="setup-step-name">{{ STEP_TITLES[guide.step] }}</span>
        </h2>
        <ol class="setup-steps">
          <li v-for="(title, i) in STEP_TITLES" :key="title">
            <button
              type="button"
              class="setup-dot"
              :class="{ active: i === guide.step, done: i <= guide.reached && guide.valid[i] && i !== guide.step }"
              :aria-current="i === guide.step ? 'step' : undefined"
              :aria-label="`${i + 1} ${title}`"
              :title="title"
              @click="guide.go(i)"
            >
              {{ i + 1 }}
            </button>
          </li>
        </ol>
        <button v-if="guide.peeking" type="button" class="btn small" @click="guide.peek(false)">Done</button>
        <IconButton kind="close" class="setup-close" label="Close" @click="guide.close()" />
      </header>
      <div class="setup-body">
        <SetupCall v-if="guide.step === 0" />
        <SetupPosition v-else-if="guide.step === 1" />
        <SetupSymbol v-else-if="guide.step === 2" />
        <SetupRadio v-else-if="guide.step === 3" />
        <SetupMap v-else />
      </div>
      <footer class="setup-foot">
        <button v-if="guide.step > 0" type="button" class="btn" @click="guide.back()">Back</button>
        <button type="submit" class="btn primary" :disabled="!guide.valid[guide.step] || guide.saving">
          {{ guide.step < LAST_STEP ? "Next" : guide.saving ? "Saving..." : "Finish" }}
        </button>
      </footer>
    </form>
  </section>
</template>
