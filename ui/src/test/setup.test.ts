// What the shared setup (setup.ts) promises: nothing a test mounts or opens runs on after the test.
import "@/test/mockmap";
import { describe, expect, it, vi } from "vitest";
import { mountApp, useAppHarness } from "@/test/app";
import { FakeSocket } from "@/test/fakesocket";
import { flushPromises } from "@vue/test-utils";

useAppHarness();

describe("what a test leaves behind", () => {
  let socket: FakeSocket | undefined;

  it("mounts the page and never unmounts it", async () => {
    mountApp();
    await flushPromises();
    socket = FakeSocket.last();
    expect(socket.closed).toBe(false);
  });

  it("finds the page of the test before it unmounted, its hub closed and its socket shut", () => {
    expect(socket?.closed).toBe(true);
  });

  it("has no real socket to open once the FakeSocket is taken away", () => {
    vi.unstubAllGlobals();
    expect(() => new WebSocket("ws://127.0.0.1:7303/ws")).toThrow("no network in the tests");
  });
});
