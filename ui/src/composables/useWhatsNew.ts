// What is new in the running version, in the update dialog's notes form: opened from Settings,
// Update check, with this version's notes, and from the line shown once after an update, with the
// notes of every version after the one this browser last saw. The browser remembers the last
// version it saw: a first visit, or a version older than the remembered one, only remembers; the
// line stays until dismissed or its notes are opened, and then that version is remembered. Without
// storage there is no line at all.
import { ref, watch, type Ref } from "vue";
import { compareVersions, isVersion } from "@/lib/releasenotes";
import { readStored, writeStored } from "@/lib/storage";

const SEEN = "seen-version";

interface NotesWanted {
  version: string;
  since: string;
}

export function useWhatsNew(version: Readonly<Ref<string>>) {
  const updatedFrom = ref<string | null>(null);
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

  function dismiss(): void {
    updatedFrom.value = null;
    writeStored(SEEN, version.value);
  }
  function show(): void {
    open.value = { version: version.value, since: "" };
  }
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
