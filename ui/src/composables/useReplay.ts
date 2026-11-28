// The clock of the map's replay and what its bar changes: the span, asked of the daemon
// (`position_history`) when the replay opens and when another span is chosen; the replay time,
// which plays from the start of the span as soon as the answer arrives; the speed in seconds of
// the span per second; play and pause; the slider, which seeks. A timer of a tenth of a second
// moves the clock (a busy map is not drawn sixty times a second); it stops at the end of the span
// and does not run while the browser tab is hidden. Only an answer that came after the asking is
// taken. When Internet stations (`igate/enabled`) or Show Internet packets heard by radio
// (`igate/show_gated`) is switched while the replay is open, the span
// is asked again, because the daemon answers another set; the new one plays on from the time it
// was at, paused if it was paused.
import { computed, onScopeDispose, ref, shallowRef, watch } from "vue";
import type { DaemonContext } from "@/composables/useDaemonContext";
import { endWithTheSocket } from "@/composables/useInFlight";
import { DEFAULT_HOURS, DEFAULT_SPEED, replayData, type ReplayData } from "@/lib/replay";

const TICK_MS = 100;

export function useReplay(
  page: Pick<DaemonContext, "send" | "positionHistory" | "igate"> & Partial<Pick<DaemonContext, "connection">>,
) {
  const hours = ref(DEFAULT_HOURS);
  const speed = ref(DEFAULT_SPEED);
  const playing = ref(false);
  const at = ref(0);
  const data = shallowRef<ReplayData | null>(null);
  const asked = ref<number | null>(null);
  let resume: { at: number; playing: boolean } | null = null;
  let timer: ReturnType<typeof setInterval> | null = null;
  let last = 0;

  function tick(): void {
    const now = Date.now();
    const gone = now - last;
    last = now;
    const span = data.value;
    if (!span || document.hidden) return;
    at.value = Math.min(span.end, at.value + gone * speed.value);
    if (at.value >= span.end) playing.value = false;
  }

  watch(playing, (on) => {
    if (timer !== null) clearInterval(timer);
    timer = null;
    if (!on) return;
    last = Date.now();
    timer = setInterval(tick, TICK_MS);
  });
  onScopeDispose(() => {
    if (timer !== null) clearInterval(timer);
  });

  watch(
    () => page.positionHistory.value,
    (message) => {
      if (!message || message.hours !== asked.value) return;
      asked.value = null;
      const span = (data.value = replayData(message));
      at.value = resume ? Math.min(span.end, Math.max(span.start, resume.at)) : span.start;
      playing.value = resume ? resume.playing : true;
      resume = null;
    },
  );

  watch(
    () => (page.igate.value ? `${page.igate.value.enabled} ${page.igate.value.show_gated}` : undefined),
    (now, before) => {
      if (now === undefined || before === undefined || (data.value === null && asked.value === null)) return;
      const was = data.value ? { at: at.value, playing: playing.value } : resume;
      ask(hours.value);
      resume = was;
    },
  );

  endWithTheSocket(page.connection, () => (asked.value = null));

  function ask(span: number = hours.value): void {
    hours.value = span;
    resume = null;
    playing.value = false;
    data.value = null;
    asked.value = page.send({ cmd: "position_history", hours: span }) ? span : null;
  }

  function stop(): void {
    playing.value = false;
    data.value = null;
    asked.value = null;
    resume = null;
  }

  function toggle(): void {
    const span = data.value;
    if (!span) return;
    if (!playing.value && at.value >= span.end) at.value = span.start;
    playing.value = !playing.value;
  }

  function pace(times: number): void {
    speed.value = times;
  }

  function seek(t: number): void {
    const span = data.value;
    if (span) at.value = Math.min(span.end, Math.max(span.start, t));
  }

  return {
    hours,
    speed,
    playing,
    at,
    data,
    loading: computed(() => asked.value !== null),
    ask,
    stop,
    toggle,
    pace,
    seek,
  };
}

export type Replay = ReturnType<typeof useReplay>;
