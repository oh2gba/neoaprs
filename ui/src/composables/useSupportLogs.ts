// The Download logs button of the Help group: it asks the daemon for the support file with the facts of this page in the request (lib/support.ts), saves the answer as a download and keeps what the group says after it: the name of the file, or why there is none.
// The button waits while the file is made; the daemon makes one file at a time.
import { computed, ref, shallowRef, type Ref } from "vue";
import { pageErrors } from "@/lib/pageerrors";
import type { Connection } from "@/lib/hub";
import { mailtoLink, pageInfo, requestBundle, saveFile, type BundleProblem } from "@/lib/support";
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
} as const satisfies Record<BundleProblem, string>;

export function useSupportLogs(given: SupportGiven, fetcher: typeof fetch = (...args) => fetch(...args)) {
  const running = ref(false);
  const saved = shallowRef<string | null>(null);
  const problem = ref("");

  async function collect(): Promise<void> {
    if (running.value) return;
    running.value = true;
    saved.value = null;
    problem.value = "";
    try {
      const info = pageInfo({
        panelWidth: given.panelWidth.value,
        connection: given.connection.value,
        daemonVersion: given.daemonVersion.value,
        errors: pageErrors.entries(),
      });
      const bundle = await requestBundle(info, given.call.value, fetcher);
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

  /** The e-mail to the project, once there is a file to attach to it. */
  const mail = computed(() =>
    saved.value === null
      ? ""
      : mailtoLink(
          [t("settings.help.mail.did"), t("settings.help.mail.expected"), t("settings.help.mail.happened"), t("settings.help.mail.when")],
          t("settings.help.mail.attach", { file: saved.value }),
        ),
  );

  return { running, saved, problem, mail, collect };
}
