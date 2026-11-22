<script setup lang="ts">
// The closed fold under an Ask: the request's Path and RF only. The path is calls or aliases
// separated by commas, or DIRECT for none; empty is each radio's own path (`usual`, null while the
// radios differ). RF only adds RFONLY after the path. An invalid path is orange with the reason in
// its title. The fold starts open when either value is not the default. While the radio carries no
// path (`disabled`) both rows are greyed with their values kept.
import { useId } from "vue";
import DisclosureBox from "@/components/DisclosureBox.vue";
import InfoTip from "@/components/InfoTip.vue";
import PathBuilder from "@/components/PathBuilder.vue";
import { requestPathProblem } from "@/composables/useRequestPath";
import { t } from "@/i18n";

const props = withDefaults(defineProps<{ path: string; rfOnly: boolean; usual: string | null; problem: string; disabled?: boolean; pathless?: string }>(), {
  disabled: false,
  pathless: undefined,
});
const emit = defineEmits<{ "update:path": [path: string]; "update:rfOnly": [on: boolean] }>();
const id = useId();
const opened = props.path.trim() !== "" || !props.rfOnly;
const about = (label: string): string => t("settings.about", { label });

function typed(event: Event): void {
  if (event.target instanceof HTMLInputElement) emit("update:path", event.target.value);
}

function ticked(event: Event): void {
  if (event.target instanceof HTMLInputElement) emit("update:rfOnly", event.target.checked);
}
</script>

<template>
  <DisclosureBox class="settings-fold" :title="t('settings.fold.advanced')" :open="opened">
    <div class="field" :class="{ invalid: problem !== '', disabled }" :title="problem || (disabled ? pathless : undefined)">
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
          :check="(text) => requestPathProblem(text, rfOnly)"
          @use="emit('update:path', $event)"
        />
        <InfoTip :label="about(t('route.path'))"
          ><span class="info-line">{{ t("route.request_path_tip") }}</span></InfoTip
        >
      </div>
    </div>
    <div class="field" :class="{ disabled }" :title="disabled ? pathless : undefined">
      <label :for="`${id}-rfonly`">{{ t("route.rf_only") }}</label>
      <div class="field-control">
        <input :id="`${id}-rfonly`" class="check" type="checkbox" :checked="rfOnly" :disabled="disabled" @change="ticked" />
        <InfoTip :label="about(t('route.rf_only'))"
          ><span class="info-line">{{ t("route.request_rf_only_tip") }}</span></InfoTip
        >
      </div>
    </div>
  </DisclosureBox>
</template>
