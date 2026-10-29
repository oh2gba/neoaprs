// The My station tab's "Choose on map": while it is on, the map waits for a click (the crosshair), and the place clicked is handed to the Beacon form, which fills our station's latitude and
// longitude with it; the user saves as for any other change. A second press of the button, or the click, ends the waiting.
import { ref } from "vue";

/** A place picked on the map; `n` counts the picks, so the same place picked twice is a change too. */
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
