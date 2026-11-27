// The daemon's times put on the page's clock: each moved by how far the page's clock was from the
// daemon's when the message came, so that an age, or a place told by its time, does not depend on
// the device's clock agreeing with the station's.

/** How far the page's clock at `nowMs` is ahead of a message sent at `at`; null when `at` is no time. */
export function clockShift(at: string, nowMs: number): number | null {
  const shift = nowMs - Date.parse(at);
  return Number.isFinite(shift) ? shift : null;
}

/** A time moved by `shiftMs`; one that is no time is left as it is. */
export function shiftedTime(iso: string, shiftMs: number): string {
  const ms = Date.parse(iso);
  return Number.isNaN(ms) ? iso : new Date(ms + shiftMs).toISOString();
}
