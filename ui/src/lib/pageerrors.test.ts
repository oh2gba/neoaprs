import { createApp, defineComponent, h } from "vue";
import { describe, expect, it, vi } from "vitest";
import { PageErrors, QUEUE_SIZE, RING_SIZE, SAME_MESSAGE_MS, SENDS_PER_MINUTE, installErrorCapture } from "@/lib/pageerrors";
import type { PageErrorCommand } from "@/protocol/protocol";

const T0 = Date.parse("2026-10-21T12:00:00Z");

/** A capture with a clock the test moves and a connection that is open or not. */
function make(open = true) {
  const clock = { now: T0 };
  const sent: PageErrorCommand[] = [];
  const link = { open };
  const errors = new PageErrors(
    () => clock.now,
    () => "index-abc123.js",
  );
  errors.attach((command) => {
    if (!link.open) return false;
    sent.push(command);
    return true;
  });
  return { errors, clock, sent, link };
}

describe("the ring of errors", () => {
  it("keeps the message, the stack, the source, the time and the component of an error, and sends it to the daemon", () => {
    const { errors, sent } = make();
    const thrown = new TypeError("x is undefined");
    errors.record(thrown, "vue", "SettingsForm");
    expect(errors.entries()).toEqual([
      {
        message: "x is undefined",
        stack: thrown.stack ?? "",
        source: "vue",
        at: "2026-10-21T12:00:00.000Z",
        last: "2026-10-21T12:00:00.000Z",
        count: 0,
        component: "SettingsForm",
      },
    ]);
    expect(sent).toEqual([
      {
        cmd: "page_error",
        message: "x is undefined (in SettingsForm)",
        stack: thrown.stack ?? "",
        source: "vue",
        at: "2026-10-21T12:00:00.000Z",
        build: "index-abc123.js",
      },
    ]);
  });

  it("takes a string, an object and a thing that cannot be written as text", () => {
    const { errors } = make();
    const loop: Record<string, unknown> = {};
    loop["me"] = loop;
    errors.record("plain words", "promise");
    errors.record({ reason: "x" }, "promise");
    errors.record(loop, "promise");
    expect(errors.entries().map((e) => e.message)).toEqual(["plain words", '{"reason":"x"}', "[object Object]"]);
  });

  it("holds the last 50", () => {
    const { errors, clock } = make();
    for (let i = 0; i < RING_SIZE + 5; i++) {
      clock.now += SAME_MESSAGE_MS; // (a minute apart, so that none is the same as the last and none hits the limit of sends)
      errors.record(new Error(`e${i}`), "window");
    }
    const messages = errors.entries().map((e) => e.message);
    expect(messages).toHaveLength(RING_SIZE);
    expect(messages[0]).toBe("e5");
    expect(messages.at(-1)).toBe(`e${RING_SIZE + 4}`);
  });

  it("cuts a message to 2000 characters, a stack to 8000 and the build to 64", () => {
    const clock = { now: T0 };
    const sent: PageErrorCommand[] = [];
    const errors = new PageErrors(
      () => clock.now,
      () => "b".repeat(100),
    );
    errors.attach((command) => sent.push(command) > 0);
    const big = Object.assign(new Error("m".repeat(5000)), { stack: "s".repeat(20000) });
    errors.record(big, "window");
    expect(sent[0]?.message).toHaveLength(2000);
    expect(sent[0]?.stack).toHaveLength(8000);
    expect(sent[0]?.build).toHaveLength(64);
  });
});

describe("the limits on the page's side", () => {
  it("counts an identical message of the last minute and does not send it again, and sends it once the minute is over", () => {
    const { errors, clock, sent } = make();
    errors.record(new Error("boom"), "vue");
    clock.now += 30_000;
    errors.record(new Error("boom"), "window");
    errors.record(new Error("boom"), "window");
    expect(sent).toHaveLength(1);
    expect(errors.entries()).toHaveLength(1);
    expect(errors.entries()[0]).toMatchObject({ count: 2, at: "2026-10-21T12:00:00.000Z", last: "2026-10-21T12:00:30.000Z" });
    clock.now += SAME_MESSAGE_MS; // (a minute after the first)
    errors.record(new Error("boom"), "window");
    expect(sent).toHaveLength(2);
    expect(errors.entries().map((e) => e.count)).toEqual([2, 0]);
  });

  it("sends at most 10 a minute, keeps the others in the ring only, and sends again in the next minute", () => {
    const { errors, clock, sent } = make();
    for (let i = 0; i < SENDS_PER_MINUTE + 5; i++) errors.record(new Error(`e${i}`), "window");
    expect(sent).toHaveLength(SENDS_PER_MINUTE);
    expect(errors.entries()).toHaveLength(SENDS_PER_MINUTE + 5);
    clock.now += SAME_MESSAGE_MS + 1;
    errors.record(new Error("later"), "window");
    expect(sent).toHaveLength(SENDS_PER_MINUTE + 1);
    expect(sent.at(-1)?.message).toBe("later");
  });

  it("holds what comes while the connection is not open, 10 at the most, and sends it when it opens", () => {
    const { errors, sent, link } = make(false);
    for (let i = 0; i < QUEUE_SIZE + 3; i++) errors.record(new Error(`e${i}`), "window");
    expect(sent).toEqual([]);
    link.open = true;
    errors.flush();
    expect(sent.map((c) => c.message)).toEqual(Array.from({ length: QUEUE_SIZE }, (_, i) => `e${i + 3}`));
    errors.flush();
    expect(sent).toHaveLength(QUEUE_SIZE); // (nothing is sent twice)
    expect(errors.entries()).toHaveLength(QUEUE_SIZE + 3);
  });

  it("sends what waited when a connection is attached", () => {
    const errors = new PageErrors(
      () => T0,
      () => "b",
    );
    errors.record(new Error("early"), "window");
    const sent: PageErrorCommand[] = [];
    errors.attach((command) => sent.push(command) > 0);
    expect(sent.map((c) => c.message)).toEqual(["early"]);
  });

  it("does not send after the connection is detached", () => {
    const { errors, sent } = make();
    errors.detach();
    errors.record(new Error("gone"), "window");
    expect(sent).toEqual([]);
    expect(errors.entries()).toHaveLength(1);
  });

  it("never throws and never loops when sending throws, and the next error is taken as usual", () => {
    const errors = new PageErrors(
      () => T0,
      () => "b",
    );
    let calls = 0;
    errors.attach(() => {
      calls += 1;
      errors.record(new Error("while reporting"), "window"); // (an error raised by the report itself is dropped)
      throw new Error("send failed");
    });
    expect(() => errors.record(new Error("first"), "window")).not.toThrow();
    expect(calls).toBe(1);
    expect(errors.entries().map((e) => e.message)).toEqual(["first"]);
    errors.record(new Error("second"), "window");
    expect(errors.entries().map((e) => e.message)).toEqual(["first", "second"]);
  });
});

describe("installErrorCapture", () => {
  it("sets the handler of Vue, which logs to the console and records the error with the component's name", () => {
    const { errors, sent } = make();
    const log = vi.spyOn(console, "error").mockImplementation(() => undefined);
    const Broken = defineComponent({
      name: "BrokenPane",
      setup() {
        throw new Error("render failed");
      },
      render: () => h("div"),
    });
    const app = createApp(Broken);
    const off = installErrorCapture(app, window, errors);
    expect(app.config.errorHandler).toBeTypeOf("function");
    app.mount(document.createElement("div"));
    expect(log).toHaveBeenCalled();
    expect(sent[0]).toMatchObject({ message: "render failed (in BrokenPane)", source: "vue" });
    off();
    log.mockRestore();
  });

  it("listens to the window's error and unhandledrejection, and stops when told", () => {
    const { errors } = make();
    const off = installErrorCapture(createApp({}), window, errors);
    window.dispatchEvent(new ErrorEvent("error", { error: new Error("from window"), message: "from window" }));
    window.dispatchEvent(new ErrorEvent("error", { message: "Script error.", filename: "https://cdn.example/x.js", lineno: 3, colno: 9 }));
    const rejection = new Event("unhandledrejection");
    Object.assign(rejection, { reason: new Error("not handled") });
    window.dispatchEvent(rejection);
    expect(errors.entries().map((e) => [e.source, e.message, e.stack.startsWith("at https://cdn.example/x.js:3:9") || e.stack.includes("Error")])).toEqual([
      ["window", "from window", true],
      ["window", "Script error.", true],
      ["promise", "not handled", true],
    ]);
    off();
    window.dispatchEvent(new ErrorEvent("error", { error: new Error("after"), message: "after" }));
    expect(errors.entries()).toHaveLength(3);
  });
});
