// The page's own errors, for fault reports: every error from Vue, the window or an unhandled
// promise goes into a ring of the last 50 (sent with the logs and in the support file as
// page-errors.json) and to the daemon as `page_error`. The same message within a minute is counted,
// not resent, and at most 10 are sent a minute. An error raised while reporting is dropped, and
// nothing here throws.
import type { App } from "vue";
import { pageBuild } from "@/lib/build";
import type { PageErrorCommand } from "@/protocol/protocol";

export type ErrorSource = PageErrorCommand["source"];

/** One error as the ring holds it. */
export interface PageErrorEntry {
  message: string;
  stack: string;
  source: ErrorSource;
  /** ISO 8601, UTC, whole seconds: when it first came. */
  at: string;
  /** When it last came, within the minute after the first. */
  last: string;
  /** How many more times it came within that minute. */
  count: number;
  /** The component a Vue error was raised in; "" for other errors or when Vue did not say. */
  component: string;
}

export const RING_SIZE = 50;
export const QUEUE_SIZE = 10;
export const SAME_MESSAGE_MS = 60_000;
export const SENDS_PER_MINUTE = 10;
const MESSAGE_MAX = 2000;
const STACK_MAX = 8000;
const BUILD_MAX = 64;

/** An instant as the wire writes it: UTC, whole seconds, `2026-11-28T11:42:06Z`. */
function wireTime(ms: number): string {
  return `${new Date(ms).toISOString().slice(0, 19)}Z`;
}

/** The words and stack of whatever was thrown: an Error, a string, or any other value. */
function describeError(thrown: unknown): { message: string; stack: string } {
  if (thrown instanceof Error) return { message: thrown.message || thrown.name, stack: thrown.stack ?? "" };
  if (typeof thrown === "string") return { message: thrown, stack: "" };
  try {
    return { message: JSON.stringify(thrown) ?? String(thrown), stack: "" };
  } catch {
    return { message: String(thrown), stack: "" };
  }
}

export class PageErrors {
  private readonly ring: PageErrorEntry[] = [];
  private readonly recent = new Map<string, { entry: PageErrorEntry; at: number }>();
  private readonly queue: PageErrorCommand[] = [];
  private sent: number[] = [];
  private sink: ((command: PageErrorCommand) => boolean) | null = null;
  private busy = false;

  constructor(
    private readonly now: () => number = Date.now,
    private readonly build: () => string = () => pageBuild(),
  ) {}

  /** The ring, oldest first. */
  entries(): PageErrorEntry[] {
    return this.ring.map((entry) => ({ ...entry }));
  }

  /**
   * Stores an error, and sends it to the daemon unless it repeats one of the last minute or the
   * minute's quota is used.
   */
  record(thrown: unknown, source: ErrorSource, component = ""): void {
    this.guarded(() => this.take(thrown, source, component));
  }

  /**
   * From now on commands go through `send`, which answers false while not connected; queued errors
   * are sent.
   */
  attach(send: (command: PageErrorCommand) => boolean): void {
    this.sink = send;
    this.flush();
  }

  detach(): void {
    this.sink = null;
  }

  /** Sends queued errors as far as the minute's limit allows. */
  flush(): void {
    this.guarded(() => this.drain());
  }

  private guarded(work: () => void): void {
    if (this.busy) return;
    this.busy = true;
    try {
      work();
    } catch {
      this.queue.length = 0; // reporting that would loop
    } finally {
      this.busy = false;
    }
  }

  private take(thrown: unknown, source: ErrorSource, component: string): void {
    const now = this.now();
    const described = describeError(thrown);
    const message = described.message.slice(0, MESSAGE_MAX);
    const same = this.recent.get(message);
    if (same && now - same.at < SAME_MESSAGE_MS) {
      same.entry.count += 1;
      same.entry.last = wireTime(now);
      return;
    }
    const at = wireTime(now);
    const stack = described.stack.slice(0, STACK_MAX);
    const entry: PageErrorEntry = { message, stack, source, at, last: at, count: 0, component };
    this.ring.push(entry);
    if (this.ring.length > RING_SIZE) this.ring.shift();
    for (const [text, seen] of this.recent) if (now - seen.at >= SAME_MESSAGE_MS) this.recent.delete(text);
    this.recent.set(message, { entry, at: now });
    if (this.queue.length >= QUEUE_SIZE) this.queue.shift();
    this.queue.push({
      cmd: "page_error",
      message: (component ? `${message} (in ${component})` : message).slice(0, MESSAGE_MAX),
      stack,
      source,
      at,
      build: this.build().slice(0, BUILD_MAX),
    });
    this.drain();
  }

  private drain(): void {
    while (this.queue.length > 0 && this.canSend()) {
      const next = this.queue[0];
      if (next === undefined || !this.transmit(next)) return; // not connected: wait
      this.queue.shift();
    }
    if (this.queue.length > 0) this.queue.length = 0; // quota used: the rest stays only in the ring
  }

  private canSend(): boolean {
    const since = this.now() - 60_000;
    this.sent = this.sent.filter((at) => at > since);
    return this.sent.length < SENDS_PER_MINUTE;
  }

  private transmit(command: PageErrorCommand): boolean {
    if (this.sink === null) return false;
    let done: boolean;
    try {
      done = this.sink(command);
    } catch {
      done = false;
    }
    if (done) this.sent.push(this.now());
    return done;
  }
}

/** The instance the page uses. */
export const pageErrors = new PageErrors();

/** The name of the component a Vue error was raised in, as far as Vue knows it. */
function componentName(instance: unknown): string {
  const options = (instance as { $options?: { name?: string; __name?: string } } | null)?.$options;
  return options?.name ?? options?.__name ?? "";
}

/**
 * Wires the capture in: Vue's error handler (logging to the console as Vue does without one), and
 * the window's `error` and `unhandledrejection`. Returns a function that removes the listeners.
 */
export function installErrorCapture(
  app: App,
  host: Pick<Window, "addEventListener" | "removeEventListener"> = window,
  errors: PageErrors = pageErrors,
): () => void {
  app.config.errorHandler = (thrown, instance, info) => {
    // eslint-disable-next-line no-console -- Vue logs an error that has no handler, and this one keeps that
    console.error(`[Vue] ${info}`, thrown);
    errors.record(thrown, "vue", componentName(instance));
  };
  const onError = (event: Event): void => {
    const { message, filename, lineno, colno } = event as ErrorEvent;
    const error: unknown = (event as ErrorEvent).error;
    if (error != null) errors.record(error, "window");
    else
      errors.record(
        Object.assign(new Error(message || "Script error."), {
          stack: filename ? `at ${filename}:${lineno}:${colno}` : "",
        }),
        "window",
      );
  };
  const onRejection = (event: Event): void => errors.record((event as PromiseRejectionEvent).reason, "promise");
  host.addEventListener("error", onError);
  host.addEventListener("unhandledrejection", onRejection);
  return () => {
    host.removeEventListener("error", onError);
    host.removeEventListener("unhandledrejection", onRejection);
  };
}
