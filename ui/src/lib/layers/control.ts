// The place of the Layers button among the map's own controls: a control of the map engine's whose box stands under the zoom buttons, in their group's look, and into which the page puts the button and its box
// (components/MapLayers.vue, by a Teleport). `place` holds the box while the control is on the map, null before and after.
import type { Ref } from "vue";
import type { IControl } from "maplibre-gl";

export function layersControl(place: Ref<HTMLElement | null>): IControl {
  return {
    onAdd: () => {
      const box = document.createElement("div");
      box.className = "maplibregl-ctrl maplibregl-ctrl-group layers-ctrl";
      place.value = box;
      return box;
    },
    onRemove: () => {
      place.value?.remove();
      place.value = null;
    },
  };
}
