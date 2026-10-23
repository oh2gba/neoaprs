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
import { t } from "@/i18n";
import { useDaemonContext } from "@/composables/useDaemonContext";
import { LAST_STEP, STEP_COUNT, stepTitle } from "@/lib/setup";

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
  <section v-if="guide.open" ref="root" class="setup" :class="{ peeking: guide.peeking }" role="dialog" :aria-label="t('setup.title')">
    <form novalidate @submit.prevent="guide.next()">
      <header class="setup-head">
        <h2>
          {{ t("setup.title") }}<span class="setup-step-name">{{ stepTitle(guide.step) }}</span>
        </h2>
        <ol class="setup-steps">
          <li v-for="i in STEP_COUNT" :key="i">
            <button
              type="button"
              class="setup-dot"
              :class="{ active: i - 1 === guide.step, done: i - 1 <= guide.reached && guide.valid[i - 1] && i - 1 !== guide.step }"
              :aria-current="i - 1 === guide.step ? 'step' : undefined"
              :aria-label="t('setup.step_label', { n: i, title: stepTitle(i - 1) })"
              :title="stepTitle(i - 1)"
              @click="guide.go(i - 1)"
            >
              {{ i }}
            </button>
          </li>
        </ol>
        <button v-if="guide.peeking" type="button" class="btn small" @click="guide.peek(false)">{{ t("setup.done") }}</button>
        <IconButton kind="close" class="setup-close" :label="t('setup.close')" @click="guide.close()" />
      </header>
      <div class="setup-body">
        <SetupCall v-if="guide.step === 0" />
        <SetupPosition v-else-if="guide.step === 1" />
        <SetupSymbol v-else-if="guide.step === 2" />
        <SetupRadio v-else-if="guide.step === 3" />
        <SetupMap v-else />
      </div>
      <footer class="setup-foot">
        <button v-if="guide.step > 0" type="button" class="btn" @click="guide.back()">{{ t("setup.back") }}</button>
        <button type="submit" class="btn primary" :disabled="!guide.valid[guide.step] || guide.saving">
          {{ guide.step < LAST_STEP ? t("setup.next") : guide.saving ? t("setup.saving") : t("setup.finish") }}
        </button>
      </footer>
    </form>
  </section>
</template>
