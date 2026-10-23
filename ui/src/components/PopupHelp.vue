<script setup lang="ts">
// "Enable pop-ups in Firefox": the steps, for the browser this is, to let it show pop-ups for the address the page was opened at (BrowserAlerts opens it from Enable pop-ups…). The host and the origin come from the address of the page,
// each with a Copy button, as the person types them into a page of the browser that this page cannot open. Once the page is reloaded as a secure context the pop-up choices are there and this panel is not shown.
// While the daemon serves https (`https.on`) the first step is the secure page, with the guide to install its certificate (HttpsGuide) below it, and the steps of http stay for whoever keeps it.
import { computed } from "vue";
import CopyField from "@/components/CopyField.vue";
import DisclosureBox from "@/components/DisclosureBox.vue";
import HttpsGuide from "@/components/HttpsGuide.vue";
import IconButton from "@/components/IconButton.vue";
import { secureUrl } from "@/lib/httpshelp";
import { browserKind, CHROMIUM, FLATPAK_COMMANDS, flagAddress, isChromium, onLinuxDesktop } from "@/lib/popuphelp";
import type { HttpsState } from "@/protocol/protocol";

const props = defineProps<{ https?: HttpsState | null }>();
const emit = defineEmits<{ close: [] }>();
const secure = computed(() => props.https?.on === true);

const userAgent = navigator.userAgent;
const kind = computed(() => browserKind(userAgent, (navigator as { brave?: unknown }).brave !== undefined));
const chromium = computed(() => (isChromium(kind.value) ? CHROMIUM[kind.value] : undefined));
/** The host name or address alone: Firefox's list is of hosts. */
const host = location.hostname;
/** Scheme, host and port: the flag of Chrome and the others is of origins. */
const origin = location.origin;
const browser = computed(() => (kind.value === "firefox" ? "Firefox" : chromium.value?.name));

function reload(): void {
  location.reload();
}
</script>

<template>
  <section class="popuphelp" aria-label="Enable pop-ups">
    <header class="popuphelp-head">
      <h4>{{ browser ? `Enable pop-ups in ${browser}` : "Enable pop-ups" }}</h4>
      <IconButton kind="close" label="Close" @click="emit('close')" />
    </header>

    <template v-if="secure && https">
      <ol class="popuphelp-steps">
        <li>
          Open the secure page: <a :href="secureUrl(https.port)">{{ secureUrl(https.port) }}</a>
        </li>
      </ol>
      <DisclosureBox title="Remove the browser's warning"><HttpsGuide :https="https" :link="false" /></DisclosureBox>
    </template>

    <component :is="secure ? 'details' : 'div'" class="popuphelp-http" :class="{ disclosure: secure }">
      <summary v-if="secure">Or keep http</summary>
      <ol v-if="kind === 'firefox'" class="popuphelp-steps">
        <li>Open a new tab, type <code class="mono">about:config</code> and press Enter, then click "Accept the Risk and Continue".</li>
        <li>Search for <code class="mono">dom.securecontext.allowlist</code>.</li>
        <li>
          If it is not there, choose "String" and click "+". Put in this and click the tick:
          <CopyField :text="host" />
          If it has text already, add a comma and this at the end.
        </li>
        <li>Come back here and <button type="button" class="btn small" @click="reload">Reload</button></li>
      </ol>

      <ol v-else-if="chromium" class="popuphelp-steps">
        <li>
          Open a new tab and paste this in the address bar:
          <CopyField :text="flagAddress(chromium.scheme)" />
        </li>
        <li>
          In the box put this, and set the choice beside it to "Enabled":
          <CopyField :text="origin" />
        </li>
        <li>Click "Relaunch" at the bottom.</li>
        <li>Come back here and <button type="button" class="btn small" @click="reload">Reload</button></li>
      </ol>

      <p v-else-if="kind === 'phone'" class="popuphelp-plain">
        Phones show pop-ups only for https pages, and this page is not one. The sound and the tab alert work here.
      </p>
      <p v-else class="popuphelp-plain">
        This browser has no way to allow pop-ups for this address. The sound and the tab alert work here. Firefox, Chrome and Edge on a computer can allow them.
      </p>

      <details v-if="kind === 'firefox' && onLinuxDesktop(userAgent)" class="popuphelp-more">
        <summary>If the pop-up still doesn't show</summary>
        <p class="popuphelp-plain">Firefox installed as a Flatpak (KDE) needs these two commands in a terminal, then a restart of Firefox:</p>
        <CopyField v-for="command in FLATPAK_COMMANDS" :key="command" :text="command" />
      </details>
    </component>
  </section>
</template>
