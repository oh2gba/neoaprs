// What is new in the version that runs, in the window of the update in its notes form (components/UpdateDialog.vue): opened from Settings → Update check, with the notes of this version, and from the line the page shows once after an
// update ("Updated to NeoAPRS 0.12.0 · What's new", components/WhatsNewLine.vue), with the notes of every version after the one this browser last saw up to this one, so that an update over several versions shows them all. The browser
// remembers the last version it saw (lib/storage.ts): a first visit only remembers this one, and so does a version older than the one remembered (a copy put back); the line stays until it is dismissed or its notes are opened, and
// then the version is remembered, so that it does not come back for that version. Without storage (a private window) there is no line at all, as on a first visit.
import { ref, watch, type Ref } from "vue";
import { compareVersions, isVersion } from "@/lib/releasenotes";
import { readStored, writeStored } from "@/lib/storage";

const SEEN = "seen-version";

/** The notes the window shows: up to `version` (the one that runs), after `since` (empty: the notes of `version` alone). */
interface NotesWanted {
  version: string;
  since: string;
}

export function useWhatsNew(version: Readonly<Ref<string>>) {
  /** The version this browser had seen before the update, while the line is up. */
  const updatedFrom = ref<string | null>(null);
  /** The notes the window shows, while it is open. */
  const open = ref<NotesWanted | null>(null);

  watch(
    version,
    (now) => {
      if (!isVersion(now)) return;
      const seen = readStored(SEEN);
      if (seen !== null && isVersion(seen) && compareVersions(now, seen) > 0) updatedFrom.value = seen;
      else {
        updatedFrom.value = null;
        writeStored(SEEN, now);
      }
    },
    { immediate: true },
  );

  /** The line goes, and does not come back for this version. */
  function dismiss(): void {
    updatedFrom.value = null;
    writeStored(SEEN, version.value);
  }
  /** The window with the notes of this version (Settings → Update check). */
  function show(): void {
    open.value = { version: version.value, since: "" };
  }
  /** The window with the notes of every version since the one this browser saw before, from the line, which goes. */
  function showUpdate(): void {
    const since = updatedFrom.value ?? "";
    dismiss();
    open.value = { version: version.value, since };
  }
  function close(): void {
    open.value = null;
  }
  return { updatedFrom, open, show, showUpdate, dismiss, close };
}
