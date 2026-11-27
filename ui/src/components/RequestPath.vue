<script setup lang="ts">
// The closed fold under an Ask: the request's Path. The path is calls or aliases separated by
// commas, or DIRECT for none; empty is each radio's own path (`usual`, null while the radios
// differ). The request always goes with RFONLY after the path. An invalid path is orange with the
// reason in its title. The fold starts open when a path is typed. While the radio carries no path
// (`disabled`) the row is greyed with its value kept.
import { useId } from "vue";
import DisclosureBox from "@/components/DisclosureBox.vue";
import InfoTip from "@/components/InfoTip.vue";
import PathBuilder from "@/components/PathBuilder.vue";
import { requestPathProblem } from "@/composables/useRequestPath";
import { t } from "@/i18n";

const props = withDefaults(
  defineProps<{
    path: string;
    usual: string | null;
    problem: string;
    disabled?: boolean;
    pathless?: string;
  }>(),
  {
    disabled: false,
    pathless: undefined,
  },
);
const emit = defineEmits<{ "update:path": [path: string] }>();
const id = useId();
const opened = props.path.trim() !== "";
const about = (label: string): string => t("settings.about", { label });

function typed(event: Event): void {
  if (event.target instanceof HTMLInputElement) emit("update:path", event.target.value);
}
</script>

<template>
  <DisclosureBox class="settings-fold" :title="t('settings.fold.advanced')" :open="opened">
    <div
      class="field"
      :class="{ invalid: problem !== '', disabled }"
      :title="problem || (disabled ? pathless : undefined)"
    >
      <label :for="`${id}-path`">{{ t("route.path") }}</label>
      <div class="field-control">
        <input
          :id="`${id}-path`"
          class="input mono"
          type="text"
          :value="path"
          :placeholder="usual === null ? t('route.default') : usual || t('route.direct')"
          :aria-invalid="problem !== ''"
          :disabled="disabled"
          autocomplete="off"
          spellcheck="false"
          @input="typed"
        />
        <PathBuilder
          :value="path"
          :usual="usual ?? ''"
          :disabled="disabled"
          :why="pathless"
          :check="requestPathProblem"
          @use="emit('update:path', $event)"
        />
        <InfoTip :label="about(t('route.path'))"
          ><span class="info-line">{{ t("route.request_path_tip") }}</span></InfoTip
        >
      </div>
    </div>
  </DisclosureBox>
</template>
