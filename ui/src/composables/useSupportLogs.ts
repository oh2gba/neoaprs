// The two ways out of the support file. Download logs asks the daemon for the file with this
// page's facts in the request (lib/support.ts), saves it as a download and keeps the file name or
// the reason there is none. Send feedback / logs asks the daemon to send the same file to the
// project with the person's words, and keeps the reference answered or the reason it was not sent;
// the dialog's file is downloaded by `collect` too, and if taken off there the words go alone
// (`send` with `file` false). Each keeps its latest outcome and waits while it works; `clear`
// takes that outcome back.
import { ref, shallowRef, type Ref } from "vue";
import { pageErrors } from "@/lib/pageerrors";
import type { Connection } from "@/lib/hub";
import { pageInfo, requestBundle, requestSend, saveFile, type SendProblem, type SentFile } from "@/lib/support";
import { t } from "@/i18n";

export interface SupportGiven {
  call: Readonly<Ref<string | null>>;
  connection: Readonly<Ref<Connection>>;
  daemonVersion: Readonly<Ref<string>>;
  panelWidth: Readonly<Ref<number>>;
}

const PROBLEMS = {
  access: "settings.help.problem.access",
  busy: "settings.help.problem.busy",
  unreachable: "settings.help.problem.unreachable",
  failed: "settings.help.problem.failed",
  offline: "settings.help.problem.offline",
  rate: "settings.help.problem.rate",
  too_large: "settings.help.problem.too_large",
  refused: "settings.help.problem.refused",
} as const satisfies Record<SendProblem, string>;

export function useSupportLogs(given: SupportGiven, fetcher: typeof fetch = (...args) => fetch(...args)) {
  const running = ref(false);
  const sending = ref(false);
  const saved = shallowRef<string | null>(null);
  const sentRef = shallowRef<string | null>(null);
  const problem = ref("");

  const info = () =>
    pageInfo({
      panelWidth: given.panelWidth.value,
      connection: given.connection.value,
      daemonVersion: given.daemonVersion.value,
      errors: pageErrors.entries(),
    });

  function clear(): void {
    saved.value = null;
    sentRef.value = null;
    problem.value = "";
  }

  /** Say whether a new try may start; clear the last outcome if it may. */
  function begin(): boolean {
    if (running.value || sending.value) return false;
    clear();
    return true;
  }

  async function collect(): Promise<void> {
    if (!begin()) return;
    running.value = true;
    try {
      const bundle = await requestBundle(info(), given.call.value, fetcher);
      if (bundle.ok) {
        saveFile(bundle.blob, bundle.filename);
        saved.value = bundle.filename;
      } else {
        problem.value = t(PROBLEMS[bundle.problem], { status: bundle.status });
      }
    } catch {
      problem.value = t(PROBLEMS.failed, { status: 0 });
    } finally {
      running.value = false;
    }
  }

  async function send(note: string, file: SentFile = true, email = ""): Promise<void> {
    if (!begin()) return;
    sending.value = true;
    try {
      const sent = await requestSend(info(), note, file, fetcher, email);
      if (sent.ok) sentRef.value = sent.ref;
      else problem.value = t(PROBLEMS[sent.problem], { status: sent.status });
    } catch {
      problem.value = t(PROBLEMS.failed, { status: 0 });
    } finally {
      sending.value = false;
    }
  }

  return { running, sending, saved, sentRef, problem, collect, send, clear };
}

export type SupportLogs = ReturnType<typeof useSupportLogs>;
