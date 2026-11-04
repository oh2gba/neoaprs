// The two ways out of the support file. Download logs (About's last line) asks the daemon for the file with the facts of this page in the request (lib/support.ts), saves the answer as a download and keeps what the line says after it: the name of the file, or why there is none.
// Send feedback / logs (the Help group) asks the daemon to send the same file to the project, with the words the person wrote in the dialog, and keeps the reference the project answers with, or why it was not sent. Only the dialog's Send does it; nothing is sent by itself. Each
// says the outcome of its latest try, and waits while it works (the daemon makes one file at a time, and says so to a second one).
import { ref, shallowRef, type Ref } from "vue";
import { pageErrors } from "@/lib/pageerrors";
import type { Connection } from "@/lib/hub";
import { pageInfo, requestBundle, requestSend, saveFile, type SendProblem } from "@/lib/support";
import { t } from "@/i18n";

/** What the group needs of the page. */
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

  /** Takes the words of the last outcome back and says whether a new try may start. */
  function begin(): boolean {
    if (running.value || sending.value) return false;
    saved.value = null;
    sentRef.value = null;
    problem.value = "";
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

  async function send(note: string): Promise<void> {
    if (!begin()) return;
    sending.value = true;
    try {
      const sent = await requestSend(info(), note, fetcher);
      if (sent.ok) sentRef.value = sent.ref;
      else problem.value = t(PROBLEMS[sent.problem], { status: sent.status });
    } catch {
      problem.value = t(PROBLEMS.failed, { status: 0 });
    } finally {
      sending.value = false;
    }
  }

  return { running, sending, saved, sentRef, problem, collect, send };
}
