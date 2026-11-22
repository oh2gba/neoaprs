<script setup lang="ts">
// The receive level of a Sound card radio, shown on the Direwolf scale (lib/soundcardlevel.ts) on a
// LevelBar. While the row is in view the page asks for the level ten times a second
// (`radio_level`); otherwise, and until the first answer, the bar shows the radio row's `rx_level`.
// The row is always present so that nothing moves when the level arrives. The bar is dimmed while
// the radio transmits. Where the card has its own capture level (`card.rx`), a CardSlider stands
// before the bar; its room is reserved whether or not the card has one.
import { computed, ref, useId } from "vue";
import CardSlider from "@/components/CardSlider.vue";
import InfoTip from "@/components/InfoTip.vue";
import LevelBar from "@/components/LevelBar.vue";
import { useDaemonContext } from "@/composables/useDaemonContext";
import { useInView } from "@/composables/useWhenShown";
import { t } from "@/i18n";
import type { SettingsFormState } from "@/composables/useSettingsForm";
import type { PageRadio } from "@/lib/radios";
import { GOOD_PERCENT, levelPercent, levelText, levelZone } from "@/lib/soundcardlevel";

const props = defineProps<{ radio: PageRadio; form: SettingsFormState }>();
const { level: lookers, radioLevels } = useDaemonContext();
const id = useId();
const bar = ref<InstanceType<typeof LevelBar> | null>(null);
const inView = useInView(computed(() => (bar.value?.$el as HTMLElement | undefined) ?? null));
lookers.look(
  () => inView.value,
  () => props.radio.id,
);
const modem = computed(() => props.radio.row.modem);
/** The level ten times a second while asked for and received; else the row's. */
const level = computed(
  () => (lookers.asked.value.includes(props.radio.id) ? radioLevels.value.get(props.radio.id) : undefined) ?? modem.value?.rx_level ?? null,
);
const zone = computed(() => (level.value === null ? "low" : levelZone(level.value)));
const fill = computed(() => (level.value === null ? 0 : levelPercent(level.value)));
const card = computed(() => (props.radio.row.card.read ? props.radio.row.card.rx : null));
const held = computed(() => modem.value !== null && (modem.value.keyed || modem.value.test !== ""));
</script>

<template>
  <LevelBar :id="id" ref="bar" :label="t('settings.scope.level')" :percent="fill" :zone="zone" :good="GOOD_PERCENT" :held="held" :value="levelText(level)"
    ><template #control><CardSlider :label="t('settings.cardlevel.rx_label')" :setting-key="`radio/${radio.id}/rx_card`" :level="card" :form="form" /></template
    ><InfoTip :label="t('settings.scope.tip_label')"
      ><span class="info-line">{{ t("settings.scope.tip1") }}</span
      ><span class="info-line">{{ t("settings.scope.tip2") }}</span></InfoTip
    ></LevelBar
  >
</template>
