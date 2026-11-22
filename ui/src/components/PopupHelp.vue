<script setup lang="ts">
// Steps for Firefox to allow notifications for this page's address, with Copy buttons for the
// values to type. Host and origin come from the page's address. While the daemon serves https,
// the first step is the secure page with its certificate guide.
import { computed } from "vue";
import CopyField from "@/components/CopyField.vue";
import DisclosureBox from "@/components/DisclosureBox.vue";
import HttpsGuide from "@/components/HttpsGuide.vue";
import IconButton from "@/components/IconButton.vue";
import RichMessage from "@/components/RichMessage.vue";
import { t } from "@/i18n";
import { secureUrl } from "@/lib/httpshelp";
import { browserKind, CHROMIUM, FLATPAK_COMMANDS, flagAddress, isChromium, onLinuxDesktop } from "@/lib/popuphelp";
import type { HttpsState } from "@/protocol/protocol";

/** What the person types into Firefox: the settings page and the setting name. */
const FIREFOX_CONFIG = "about:config";
const FIREFOX_KEY = "dom.securecontext.allowlist";

const props = defineProps<{ https?: HttpsState | null }>();
const emit = defineEmits<{ close: [] }>();
const secure = computed(() => props.https?.on === true);

const userAgent = navigator.userAgent;
const kind = computed(() => browserKind(userAgent, (navigator as { brave?: unknown }).brave !== undefined));
const chromium = computed(() => (isChromium(kind.value) ? CHROMIUM[kind.value] : undefined));
/** The host name or address alone, as Firefox's list holds hosts. */
const host = location.hostname;
/** Scheme, host and port, as the flag of Chrome and others holds origins. */
const origin = location.origin;
const browser = computed(() => (kind.value === "firefox" ? "Firefox" : chromium.value?.name));

function reload(): void {
  location.reload();
}
</script>

<template>
  <section class="popuphelp" :aria-label="t('help.popup.title')">
    <header class="popuphelp-head">
      <h4>{{ browser ? t("help.popup.title_in", { browser }) : t("help.popup.title") }}</h4>
      <IconButton kind="close" :label="t('help.close')" @click="emit('close')" />
    </header>

    <template v-if="secure && https">
      <ol class="popuphelp-steps">
        <li>
          <RichMessage id="help.popup.secure_page"
            ><template #link
              ><a :href="secureUrl(https.port)">{{ secureUrl(https.port) }}</a></template
            ></RichMessage
          >
        </li>
      </ol>
      <DisclosureBox :title="t('help.popup.remove_warning')"><HttpsGuide :https="https" :link="false" /></DisclosureBox>
    </template>

    <component :is="secure ? DisclosureBox : 'div'" class="popuphelp-http" v-bind="secure ? { title: t('help.popup.keep_http') } : {}">
      <ol v-if="kind === 'firefox'" class="popuphelp-steps">
        <li>
          <RichMessage id="help.popup.firefox1"
            ><template #config
              ><code class="mono">{{ FIREFOX_CONFIG }}</code></template
            ></RichMessage
          >
        </li>
        <li>
          <RichMessage id="help.popup.firefox2"
            ><template #key
              ><code class="mono">{{ FIREFOX_KEY }}</code></template
            ></RichMessage
          >
        </li>
        <li>
          {{ t("help.popup.firefox3a") }}
          <CopyField :text="host" />
          {{ t("help.popup.firefox3b") }}
        </li>
        <li>
          <RichMessage id="help.popup.back"
            ><template #reload
              ><button type="button" class="btn small" @click="reload">{{ t("help.popup.reload") }}</button></template
            ></RichMessage
          >
        </li>
      </ol>

      <ol v-else-if="chromium" class="popuphelp-steps">
        <li>
          {{ t("help.popup.chromium1") }}
          <CopyField :text="flagAddress(chromium.scheme)" />
        </li>
        <li>
          {{ t("help.popup.chromium2") }}
          <CopyField :text="origin" />
        </li>
        <li>{{ t("help.popup.chromium3") }}</li>
        <li>
          <RichMessage id="help.popup.back"
            ><template #reload
              ><button type="button" class="btn small" @click="reload">{{ t("help.popup.reload") }}</button></template
            ></RichMessage
          >
        </li>
      </ol>

      <p v-else-if="kind === 'phone'" class="popuphelp-plain">{{ t("help.popup.phone") }}</p>
      <p v-else class="popuphelp-plain">{{ t("help.popup.other") }}</p>

      <DisclosureBox v-if="kind === 'firefox' && onLinuxDesktop(userAgent)" plain class="popuphelp-more" :title="t('help.popup.still')">
        <p class="popuphelp-plain">{{ t("help.popup.flatpak") }}</p>
        <CopyField v-for="command in FLATPAK_COMMANDS" :key="command" :text="command" />
      </DisclosureBox>
    </component>
  </section>
</template>
