<script setup lang="ts">
// The closed fold under an Ask (Ask around in the Nearby tab, Local info in the Objects tab), as the object form's Advanced: the **Path** the request goes by and **RF only**. The path is calls or aliases separated by commas (an explicit
// OH2RDK-7,OH2RCH-2 for a station that a fill-in digipeater relays only when it is named, WIDE1-1,WIDE2-1) or DIRECT for none; empty is the request's own default (`usual`, empty for direct), which the placeholder shows. The path
// builder's button (PathBuilder) beside the field builds one to put in it, held to the same rule. RF only (ticked unless the person
// unticks it) puts RFONLY after the path, so that the iGates keep the request off the internet. A path that cannot go is orange with the reason in its title, as the other path fields are, and the caller keeps Ask off with the same
// reason. The fold starts open when either is not the default, so that what will be sent is in sight; its title never changes. While the radio the request goes on carries no path (`disabled`), both rows are greyed in their places
// with their values kept, as Route's are, and nothing in them is marked wrong.
import { useId } from "vue";
import DisclosureBox from "@/components/DisclosureBox.vue";
import InfoTip from "@/components/InfoTip.vue";
import PathBuilder from "@/components/PathBuilder.vue";
import { requestPathProblem } from "@/composables/useRequestPath";
import { t } from "@/i18n";

const props = withDefaults(defineProps<{ path: string; rfOnly: boolean; usual: string; problem: string; disabled?: boolean }>(), { disabled: false });
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
    <div class="field" :class="{ invalid: problem !== '', disabled }" :title="problem || undefined">
      <label :for="`${id}-path`">{{ t("route.path") }}</label>
      <div class="field-control">
        <input
          :id="`${id}-path`"
          class="input mono"
          type="text"
          :value="path"
          :placeholder="usual || t('route.direct')"
          :aria-invalid="problem !== ''"
          :disabled="disabled"
          autocomplete="off"
          spellcheck="false"
          @input="typed"
        />
        <PathBuilder :value="path" :usual="usual" :disabled="disabled" :check="(text) => requestPathProblem(text, rfOnly)" @use="emit('update:path', $event)" />
        <InfoTip :label="about(t('route.path'))"
          ><span class="info-line">{{ t("route.request_path_tip") }}</span></InfoTip
        >
      </div>
    </div>
    <div class="field" :class="{ disabled }">
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
