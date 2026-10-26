<script setup lang="ts">
// The choice of the page's language, at the top of the Settings tab: one list, every language by its own name. It is kept in this browser (src/i18n), not on the daemon, so each device decides; until it is chosen the page follows the browser's own languages.
import InfoTip from "@/components/InfoTip.vue";
import { availableLocales, locale, setLocale, t } from "@/i18n";

function choose(event: Event): void {
  const select = event.target;
  if (select instanceof HTMLSelectElement) setLocale(select.value, true);
}
</script>

<template>
  <div class="field">
    <label for="language">{{ t("settings.language.label") }}</label>
    <div class="field-control">
      <select id="language" class="input" :value="locale" @change="choose">
        <option v-for="l in availableLocales()" :key="l.code" :value="l.code" :lang="l.code">{{ l.name }}</option>
      </select>
      <InfoTip :label="t('settings.about', { label: t('settings.language.label') })">
        <span class="info-line">{{ t("settings.language.tip1") }}</span>
      </InfoTip>
    </div>
  </div>
</template>
