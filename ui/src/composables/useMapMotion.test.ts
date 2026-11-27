import { describe, expect, it } from "vitest";
import { effectScope, nextTick, ref } from "vue";
import { FRAME_MS, useMapMotion, type Frames, type Mover } from "@/composables/useMapMotion";

/** Frames that run when the test says, on a clock the test moves. */
function fakeFrames() {
  let waiting = new Map<number, () => void>();
  let next = 1;
  let clock = 1_000_000;
  const frames: Frames = {
    request: (step) => {
      waiting.set(next, step);
      return next++;
    },
    cancel: (id) => void waiting.delete(id),
    now: () => clock,
  };
  const run = (ms: number): void => {
    clock += ms;
    const due = waiting;
    waiting = new Map();
    for (const step of due.values()) step();
  };
  return { frames, run, pending: () => waiting.size };
}

function mover(on = false) {
  const active = ref(on);
  const drawn: number[] = [];
  const it: Mover = { active: () => active.value, draw: (now) => void drawn.push(now) };
  return { active, drawn, it };
}

describe("useMapMotion", () => {
  it("asks for no frame while nothing is active, and starts when a mover becomes active", async () => {
    const fake = fakeFrames();
    const one = mover();
    const motion = effectScope().run(() => useMapMotion([one.it], fake.frames));
    expect(fake.pending()).toBe(0);
    expect(motion?.running()).toBe(false);
    one.active.value = true;
    await nextTick();
    expect(fake.pending()).toBe(1);
    fake.run(16);
    expect(one.drawn).toHaveLength(1);
  });

  it("draws at most every FRAME_MS however often the frames come", () => {
    const fake = fakeFrames();
    const one = mover(true);
    effectScope().run(() => useMapMotion([one.it], fake.frames));
    for (let i = 0; i < 30; i++) fake.run(10);
    expect(one.drawn.length).toBe(Math.floor((30 * 10) / FRAME_MS));
    for (let i = 1; i < one.drawn.length; i++) expect(one.drawn[i] - one.drawn[i - 1]).toBeGreaterThanOrEqual(FRAME_MS);
  });

  it("draws only the active movers, one clock for all", () => {
    const fake = fakeFrames();
    const traffic = mover(true);
    const satellites = mover(false);
    effectScope().run(() => useMapMotion([traffic.it, satellites.it], fake.frames));
    fake.run(FRAME_MS);
    expect(traffic.drawn).toHaveLength(1);
    expect(satellites.drawn).toHaveLength(0);
  });

  it("leaves no frame asked for when every mover goes off (the layer off, the tab hidden)", async () => {
    const fake = fakeFrames();
    const one = mover(true);
    const motion = effectScope().run(() => useMapMotion([one.it], fake.frames));
    fake.run(FRAME_MS);
    one.active.value = false;
    await nextTick();
    expect(fake.pending()).toBe(0);
    expect(motion?.running()).toBe(false);
    fake.run(FRAME_MS);
    expect(one.drawn).toHaveLength(1);
  });

  it("stops with its scope", () => {
    const fake = fakeFrames();
    const one = mover(true);
    const scope = effectScope();
    scope.run(() => useMapMotion([one.it], fake.frames));
    expect(fake.pending()).toBe(1);
    scope.stop();
    expect(fake.pending()).toBe(0);
  });
});
