// What the Help group of the Settings tab needs to ask the daemon for the support file: the facts of this page that the daemon cannot know (`pageInfo`), the request (`requestBundle`: `POST support/bundle` with the same cookie as the page), the name of
// the file it answers with, the saving of it as a download and the e-mail that goes with it. The daemon makes the zip (the log, the settings without the access key, the packets); the page adds page.json and page-errors.json to it by sending `page`.
import { endpoint } from "@/lib/access";
import { PAGE_VERSION, pageBuild } from "@/lib/build";
import { sizeOf, type SizeClass } from "@/lib/layout";
import type { Connection } from "@/lib/hub";
import type { PageErrorEntry } from "@/lib/pageerrors";

export const SUPPORT_ADDRESS = "neoaprs@oh2gba.eu";
export const SUPPORT_MANUAL = "https://github.com/oh2gba/neoaprs/blob/master/docs/manual/support.md";
/** The daemon takes a body of 256 KB at the most; the page keeps under it and cuts the errors, not the facts. */
export const BODY_MAX_BYTES = 240_000;

export interface PageInfo {
  version: string;
  build: string;
  daemonVersion: string;
  userAgent: string;
  language: string;
  timeZone: string;
  /** `Date.now()` of this browser, and the same as ISO 8601 */
  timeMs: number;
  time: string;
  viewport: { width: number; height: number };
  panelWidth: number;
  sizeClass: SizeClass;
  darkScheme: boolean;
  standalone: boolean;
  serviceWorkerControlled: boolean;
  connection: Connection;
  errors: PageErrorEntry[];
}

/** What the browser says of itself; the tests give a stand-in. */
export interface InfoHost {
  navigator: { userAgent: string; language: string; standalone?: boolean; serviceWorker?: { controller: unknown } };
  innerWidth: number;
  innerHeight: number;
  matchMedia?: (query: string) => { matches: boolean };
  document: Document;
}

export interface InfoGiven {
  panelWidth: number;
  connection: Connection;
  daemonVersion: string;
  errors: PageErrorEntry[];
}

function timeZone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone;
  } catch {
    return "";
  }
}

/** The facts about this page and this browser that the support file carries as page.json. */
export function pageInfo(given: InfoGiven, host: InfoHost = window, now: number = Date.now()): PageInfo {
  const matches = (query: string): boolean => host.matchMedia?.(query).matches ?? false;
  return {
    version: PAGE_VERSION,
    build: pageBuild(host.document),
    daemonVersion: given.daemonVersion,
    userAgent: host.navigator.userAgent,
    language: host.navigator.language,
    timeZone: timeZone(),
    timeMs: now,
    time: new Date(now).toISOString(),
    viewport: { width: host.innerWidth, height: host.innerHeight },
    panelWidth: given.panelWidth,
    sizeClass: sizeOf(host.innerWidth, host.innerHeight),
    darkScheme: matches("(prefers-color-scheme: dark)"),
    standalone: matches("(display-mode: standalone)") || host.navigator.standalone === true,
    serviceWorkerControlled: Boolean(host.navigator.serviceWorker?.controller),
    connection: given.connection,
    errors: given.errors,
  };
}

/** The request body: when it is over the daemon's limit the stacks of the errors are cut short, then the oldest errors go. */
export function bodyOf(info: PageInfo): string {
  const size = (text: string): number => new TextEncoder().encode(text).length;
  let body = JSON.stringify({ page: info });
  if (size(body) <= BODY_MAX_BYTES) return body;
  let errors = info.errors.map((entry) => ({ ...entry, stack: entry.stack.slice(0, 500) }));
  body = JSON.stringify({ page: { ...info, errors } });
  while (size(body) > BODY_MAX_BYTES && errors.length > 0) {
    errors = errors.slice(1);
    body = JSON.stringify({ page: { ...info, errors } });
  }
  return body;
}

export type BundleProblem = "access" | "busy" | "unreachable" | "failed";

export type Bundle = { ok: true; blob: Blob; filename: string } | { ok: false; problem: BundleProblem; status: number };

const pad = (n: number): string => String(n).padStart(2, "0");

/** The name the daemon gives (`neoaprs-support-CALL-YYYYmmdd-HHMMSSZ.zip`) when it did not say, made the same way from this browser's clock. */
export function madeName(call: string | null, now: number): string {
  const d = new Date(now);
  const stamp = `${d.getUTCFullYear()}${pad(d.getUTCMonth() + 1)}${pad(d.getUTCDate())}-${pad(d.getUTCHours())}${pad(d.getUTCMinutes())}${pad(d.getUTCSeconds())}Z`;
  return `neoaprs-support-${call ? `${call.replace(/[^\w-]/g, "")}-` : ""}${stamp}.zip`;
}

/** The file name of a Content-Disposition header, kept to plain characters; null when there is none. */
export function filenameOf(disposition: string | null): string | null {
  const found = /filename\*?=(?:UTF-8'')?"?([^";]+)"?/i.exec(disposition ?? "");
  const name = (found?.[1] ?? "")
    .trim()
    .replace(/^.*[\\/]/, "")
    .replace(/[^\w.-]/g, "_");
  return name === "" || /^\.+$/.test(name) ? null : name;
}

/** Asks the daemon for the support file. The daemon's 401 and 403 are no access, its 429 is another file being made; no answer at all is an unreachable daemon. */
export async function requestBundle(info: PageInfo, call: string | null, fetcher: typeof fetch = fetch, now: number = Date.now()): Promise<Bundle> {
  let response: Response;
  try {
    response = await fetcher(endpoint("support/bundle"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: bodyOf(info),
      credentials: "same-origin",
      cache: "no-store",
    });
  } catch {
    return { ok: false, problem: "unreachable", status: 0 };
  }
  if (response.status === 401 || response.status === 403) return { ok: false, problem: "access", status: response.status };
  if (response.status === 429) return { ok: false, problem: "busy", status: 429 };
  if (!response.ok) return { ok: false, problem: "failed", status: response.status };
  try {
    const blob = await response.blob();
    return { ok: true, blob, filename: filenameOf(response.headers.get("Content-Disposition")) ?? madeName(call, now) };
  } catch {
    return { ok: false, problem: "unreachable", status: 0 };
  }
}

/** Saves a file the way a link to it would: an object URL, a click on a link that downloads, and the URL given back a moment later. */
export function saveFile(blob: Blob, filename: string, doc: Document = document, urls: Pick<typeof URL, "createObjectURL" | "revokeObjectURL"> = URL): void {
  const url = urls.createObjectURL(blob);
  const link = doc.createElement("a");
  link.href = url;
  link.download = filename;
  link.rel = "noopener";
  link.hidden = true;
  doc.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => urls.revokeObjectURL(url), 1000);
}

/** The e-mail to the project: the subject starts with the version, for the person to finish, and the body is a form to fill in. `labels` are the words of the page's language, in the order of the form; `attach` is the line that reminds of the file, left out (null) before there is one. */
export function mailtoLink(labels: readonly string[], attach: string | null): string {
  const body = labels
    .flatMap((label) => [label, ""])
    .concat(attach === null ? [] : [attach])
    .join("\r\n")
    .trimEnd();
  return `mailto:${SUPPORT_ADDRESS}?subject=${encodeURIComponent(`NeoAPRS ${PAGE_VERSION}: `)}&body=${encodeURIComponent(body)}`;
}
