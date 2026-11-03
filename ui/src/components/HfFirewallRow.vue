<script setup lang="ts">
// The Fix button of the HF radio's box, an ActionRow above Tune that is there only while the Mercury program is not started for the Windows Firewall's sake (the status line above it says so; lib/tncstatus.ts `firewallFixable`). A press asks the daemon to make the Windows Firewall
// rule that keeps the network from Mercury (`hf_allow_firewall`): Windows asks for the operator's permission, and when the rule is in force the HF radio starts by itself and the row goes. A declined prompt leaves everything as it was. The button waits while the daemon
// is at it (`modem.allowing`, which every page shows).
import { computed } from "vue";
import ActionRow from "@/components/ActionRow.vue";
import { useDaemonContext } from "@/composables/useDaemonContext";
import { t } from "@/i18n";

defineProps<{ id: string }>();
const { hf, send } = useDaemonContext();
const working = computed(() => hf.value?.modem?.allowing === true);

function fix(): void {
  if (working.value) return;
  send({ cmd: "hf_allow_firewall" });
}
</script>

<template>
  <ActionRow :id="id" :label="t('settings.firewall.label')" :tip-label="t('settings.firewall.tip_label')">
    <button :id="id" class="btn" type="button" :disabled="working" @click="fix">{{ t("settings.firewall") }}</button>
    <template #tip
      ><span class="info-line">{{ t("settings.firewall.tip1") }}</span></template
    >
  </ActionRow>
</template>
