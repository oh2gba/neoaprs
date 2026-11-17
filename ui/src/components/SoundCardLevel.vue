<script setup lang="ts">
// The receive level of a Sound card radio, a row of its box: the level Direwolf hears now, on Direwolf's own scale (lib/soundcardlevel.ts), on the bar of components/LevelBar.vue. While the row is in view
// (composables/useWhenShown.ts `useInView`) the page asks for the level ten times a second (`radio_level`, counted with the other panes in composables/useRadioAsks.ts) and the bar follows it; else, and until the
// first one comes, the bar is the modem's `rx_level` of the radio's row, every two seconds and at each packet.
// The row is there while Direwolf does not run, with its room kept, so that nothing moves when the level comes; the bar is dimmed while the radio transmits (or is tuned), when the level is the last one heard. Its (i) is
// the receive level's of the HF box: the same words hold for both. Where the radio's sound card has a capture level of its own (the row's `card.rx`, once its levels are known: `card.read`) its slider stands
// before the bar (components/CardSlider.vue, the radio's `rx_card`): the slider sets what the card takes from the radio, the bar shows what comes out. The slider's room is there whatever the card has, so
// that the bar never changes its width or place when the slider comes.
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
/** The level ten times a second while it is asked for and has come; else the row's. */
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
