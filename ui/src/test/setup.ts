import { afterEach } from "vitest";
import { setLocale } from "@/i18n";

// Nothing leaves the machine in a test: a fetch that a test has not replaced fails, whatever address the page has.
globalThis.fetch = () => Promise.reject(new Error("no network in the tests: give the code a fetch of its own"));

// The tests read English, whatever the browser of the machine says: the language is pinned to it before a file runs and after each test (a test of another language sets its own, and storage is the test's to clear).
setLocale("en");
afterEach(() => setLocale("en"));
