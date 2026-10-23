// The page's service worker (ui/sw/sw.js, built as sw.js beside index.html): it lets a browser install the page as an app and open its shell while the daemon is away. Browsers allow a worker only on a secure origin: https and
// localhost. Over plain http from another computer (the Raspberry Pi's address) there is none, and that is not an error: nothing is registered and nothing is said.
export interface WorkerHost {
  navigator: { serviceWorker?: { register: (url: string) => Promise<unknown> } };
  isSecureContext: boolean;
  addEventListener: (type: "load", listener: () => void) => void;
  document: { readyState: string };
}

/** Can this page have a worker? */
export function canHaveWorker(host: Pick<WorkerHost, "navigator" | "isSecureContext"> = window): boolean {
  return "serviceWorker" in host.navigator && host.isSecureContext;
}

/** Registers sw.js once the page has loaded, so that the worker never slows the first paint; the address is relative, which is the page's own folder, and so its scope. A refusal is silent. */
export function registerWorker(host: WorkerHost = window): boolean {
  const container = host.navigator.serviceWorker;
  if (!container || !canHaveWorker(host)) return false;
  const go = (): void => void container.register("./sw.js").catch(() => undefined);
  if (host.document.readyState === "complete") go();
  else host.addEventListener("load", go);
  return true;
}
