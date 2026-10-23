// The chime of the page's alert, made with the Web Audio API when it plays (two short soft tones, a rising fourth): no sound file. A browser lets a page make sound only after a click or a key press, so `unlock`
// is called from the first one, and `play` makes no sound, and says so, while the audio is still locked.
const NOTES: readonly (readonly [hz: number, at: number])[] = [
  [784, 0],
  [1047, 0.16],
];
const NOTE_SEC = 0.45;
const PEAK = 0.18;

interface AudioWindow {
  AudioContext?: typeof AudioContext;
  webkitAudioContext?: typeof AudioContext;
}

export class Chime {
  private context: AudioContext | null = null;

  /** Makes the audio context (inside a click or a key press) and lets it run; false when the browser has none or does not let it run. */
  async unlock(): Promise<boolean> {
    try {
      if (this.context === null) {
        const w = window as unknown as AudioWindow;
        const Context = w.AudioContext ?? w.webkitAudioContext;
        if (Context === undefined) return false;
        this.context = new Context();
      }
      if (this.context.state !== "running") await this.context.resume();
      return this.context.state === "running";
    } catch {
      return false;
    }
  }

  get unlocked(): boolean {
    return this.context?.state === "running";
  }

  /** Plays the chime; false, and silent, while the audio is locked. */
  play(): boolean {
    const context = this.context;
    if (context === null || context.state !== "running") return false;
    try {
      const start = context.currentTime;
      for (const [hz, at] of NOTES) {
        const tone = context.createOscillator();
        const level = context.createGain();
        tone.type = "sine";
        tone.frequency.value = hz;
        level.gain.setValueAtTime(0.0001, start + at);
        level.gain.exponentialRampToValueAtTime(PEAK, start + at + 0.02);
        level.gain.exponentialRampToValueAtTime(0.0001, start + at + NOTE_SEC);
        tone.connect(level);
        level.connect(context.destination);
        tone.start(start + at);
        tone.stop(start + at + NOTE_SEC + 0.05);
      }
      return true;
    } catch {
      return false;
    }
  }
}
