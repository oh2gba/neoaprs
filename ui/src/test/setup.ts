import { enableAutoUnmount } from "@vue/test-utils";
import { afterEach } from "vitest";
import { setLocale } from "@/i18n";

// No network in a test: a fetch a test has not replaced fails.
globalThis.fetch = () => Promise.reject(new Error("no network in the tests: give the code a fetch of its own"));

// The tests read English whatever the browser says: pin the language before a file runs and after
// each test.
setLocale("en");
afterEach(() => setLocale("en"));

// A real socket is never opened either: a running page would reach the machine's daemon. Tests that
// need a socket use FakeSocket.
globalThis.WebSocket = class {
  constructor() {
    throw new Error("no network in the tests: give the code a socket of its own");
  }
} as unknown as typeof WebSocket;

// Whatever a test mounts is unmounted when it ends, so nothing runs on after the file's environment
// is gone.
enableAutoUnmount(afterEach);
