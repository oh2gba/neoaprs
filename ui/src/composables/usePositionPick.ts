// The My station tab's "Choose on map": while on, the map waits for a click (crosshair) and hands
// the place to the Beacon form. A second press of the button, or the click, ends the waiting.
import { ref } from "vue";

export interface Picked {
  lat: number;
  lon: number;
  n: number;
}

export function usePositionPick() {
  const picking = ref(false);
  const picked = ref<Picked | null>(null);
  let n = 0;
  return {
    picking,
    picked,
    toggle(): void {
      picking.value = !picking.value;
    },
    place(lat: number, lon: number): void {
      picked.value = { lat, lon, n: ++n };
      picking.value = false;
    },
  };
}
