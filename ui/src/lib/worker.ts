// The page's service worker (ui/sw/sw.js, built beside index.html): it lets a browser install the
// page as an app and open its shell while the daemon is away. Browsers allow a worker only on a
// secure origin (https or localhost); over plain http from another computer none is registered,
// and that is not an error.
export interface WorkerHost {
  navigator: { serviceWorker?: { register: (url: string) => Promise<unknown> } };
  isSecureContext: boolean;
  addEventListener: (type: "load", listener: () => void) => void;
  document: { readyState: string };
}

/** Whether this page can have a worker. */
export function canHaveWorker(host: Pick<WorkerHost, "navigator" | "isSecureContext"> = window): boolean {
  return "serviceWorker" in host.navigator && host.isSecureContext;
}

/**
 * Register sw.js once the page has loaded, so the worker never slows the first paint. The address
 * is relative, so the page's own folder is the scope. A refusal is silent.
 */
export function registerWorker(host: WorkerHost = window): boolean {
  const container = host.navigator.serviceWorker;
  if (!container || !canHaveWorker(host)) return false;
  const go = (): void => void container.register("./sw.js").catch(() => undefined);
  if (host.document.readyState === "complete") go();
  else host.addEventListener("load", go);
  return true;
}
