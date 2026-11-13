import { enableAutoUnmount } from "@vue/test-utils";
import { afterEach } from "vitest";
import { setLocale } from "@/i18n";

// Nothing leaves the machine in a test: a fetch that a test has not replaced fails, whatever address the page has.
globalThis.fetch = () => Promise.reject(new Error("no network in the tests: give the code a fetch of its own"));

// The tests read English, whatever the browser of the machine says: the language is pinned to it before a file runs and after each test (a test of another language sets its own, and storage is the test's to clear).
setLocale("en");
afterEach(() => setLocale("en"));

// A real socket is never opened either: a page that is left running would open one to whatever listens on the address of the tests (the daemon of the machine), and a hello from it would reach a test file that has ended. The tests that need a socket put in the FakeSocket (vi.stubGlobal puts this back after each test).
globalThis.WebSocket = class {
  constructor() {
    throw new Error("no network in the tests: give the code a socket of its own");
  }
} as unknown as typeof WebSocket;

// Whatever a test mounts is unmounted when the test ends, whatever the file does or forgets: the page's hub closes its socket and stops its timers, a composable's listeners and intervals are taken away, so nothing runs on after the file's environment is gone.
enableAutoUnmount(afterEach);
