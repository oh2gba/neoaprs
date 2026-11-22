// The page's alert dependencies made by hand: an audio context locked until resumed, a Notification
// that keeps what was shown, the page's address and whether it is in front.
import { vi } from "vitest";

export class FakeAudioContext {
  static made: FakeAudioContext[] = [];
  static afterResume: AudioContextState = "running";
  state: AudioContextState = "suspended";
  currentTime = 0;
  destination = {};
  oscillators = 0;

  constructor() {
    FakeAudioContext.made.push(this);
  }

  resume(): Promise<void> {
    this.state = FakeAudioContext.afterResume;
    return Promise.resolve();
  }

  createOscillator() {
    this.oscillators++;
    return { type: "", frequency: { value: 0 }, connect: vi.fn(), start: vi.fn(), stop: vi.fn() };
  }

  createGain() {
    return { gain: { setValueAtTime: vi.fn(), exponentialRampToValueAtTime: vi.fn() }, connect: vi.fn() };
  }

  static reset(): void {
    FakeAudioContext.made = [];
    FakeAudioContext.afterResume = "running";
  }

  static played(): number {
    return FakeAudioContext.made.reduce((sum, context) => sum + context.oscillators, 0);
  }
}

export class FakeNotification {
  static shown: FakeNotification[] = [];
  static permission: NotificationPermission = "default";
  static answer: NotificationPermission = "granted";
  static asked = 0;
  static refuses = false;
  onclick: (() => void) | null = null;
  onerror: (() => void) | null = null;
  closed = false;

  constructor(
    readonly title: string,
    readonly options: NotificationOptions = {},
  ) {
    if (FakeNotification.refuses) throw new TypeError("Illegal constructor");
    FakeNotification.shown.push(this);
  }

  close(): void {
    this.closed = true;
  }

  static requestPermission(): Promise<NotificationPermission> {
    FakeNotification.asked++;
    FakeNotification.permission = FakeNotification.answer;
    return Promise.resolve(FakeNotification.answer);
  }

  static reset(permission: NotificationPermission = "default"): void {
    FakeNotification.shown = [];
    FakeNotification.permission = permission;
    FakeNotification.answer = "granted";
    FakeNotification.asked = 0;
    FakeNotification.refuses = false;
  }
}

export function stubBrowser(options: { secure?: boolean; notifications?: boolean } = {}): void {
  FakeAudioContext.reset();
  FakeNotification.reset();
  vi.stubGlobal("AudioContext", FakeAudioContext);
  vi.stubGlobal("isSecureContext", options.secure ?? true);
  if (options.notifications ?? true) vi.stubGlobal("Notification", FakeNotification);
}

/**
 * The page is opened in a browser at this address; clears the app-window mark a test may have left.
 */
export function openedAt(host: string): void {
  sessionStorage.removeItem(IN_APP);
  (window as unknown as { happyDOM: { setURL(url: string): void } }).happyDOM.setURL(`http://${host}:7303/`);
}

const IN_APP = "neoaprs-in-app";

/**
 * The page is the desktop app's window: the loopback page with the window's fragment, in the web
 * engine of `userAgent`.
 */
export function openedInApp(userAgent?: string): void {
  sessionStorage.removeItem(IN_APP);
  (window as unknown as { happyDOM: { setURL(url: string): void } }).happyDOM.setURL("http://127.0.0.1:7303/#app");
  if (userAgent !== undefined) vi.stubGlobal("navigator", { userAgent });
}

/** The user agents of the app's windows: Qt's web engine, WebView2, and the system web engine. */
export const APP_WINDOWS = {
  "Linux, Qt":
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) QtWebEngine/6.140.0 Chrome/140.0.0.0 Safari/537.36",
  "macOS, Qt":
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) QtWebEngine/6.140.0 Chrome/140.0.0.0 Safari/537.36",
  "Windows, WebView2":
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36 Edg/142.0.0.0",
  "Linux, WebKitGTK":
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Safari/605.1.15",
  "macOS, WKWebView": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko)",
} as const;

export function setSeen(seen: boolean): void {
  Object.defineProperty(document, "visibilityState", { configurable: true, get: () => (seen ? "visible" : "hidden") });
  vi.spyOn(document, "hasFocus").mockReturnValue(seen);
}

export function resetSeen(): void {
  Reflect.deleteProperty(document, "visibilityState");
  vi.restoreAllMocks();
  openedAt("127.0.0.1");
}
