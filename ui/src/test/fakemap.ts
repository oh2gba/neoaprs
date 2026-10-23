// A stand-in for MapLibre in the component tests (there is no WebGL in the test browser): it keeps what the page asked of it and lets a test fire the map's events. The component gets it
// through a mock of "@/lib/basemap".
import { vi } from "vitest";

export const fakeState = { archive: true, world: false, engine: true };

type Handler = (event?: unknown) => void;

export class FakeMap {
  static all: FakeMap[] = [];
  handlers = new Map<string, Handler[]>();
  sources = new Map<string, { setData: ReturnType<typeof vi.fn> }>();
  layers: string[] = [];
  zoom: number;
  center: { lng: number; lat: number };
  flights: unknown[] = [];
  jumps: unknown[] = [];
  styles: unknown[] = [];
  removed = false;
  touchZoomRotate = { disableRotation: vi.fn() };

  constructor(readonly options: { center: [number, number]; zoom: number; style: unknown }) {
    this.zoom = options.zoom;
    this.center = { lng: options.center[0], lat: options.center[1] };
    this.styles.push(options.style);
    FakeMap.all.push(this);
  }

  static last(): FakeMap {
    const map = FakeMap.all[FakeMap.all.length - 1];
    if (!map) throw new Error("no map was made");
    return map;
  }

  on(event: string, handler: Handler): this {
    this.handlers.set(event, [...(this.handlers.get(event) ?? []), handler]);
    return this;
  }

  fire(event: string, payload?: unknown): void {
    for (const handler of this.handlers.get(event) ?? []) handler(payload);
  }

  addControl(): void {}
  addSource(id: string): void {
    this.sources.set(id, { setData: vi.fn() });
  }
  addLayer(layer: { id: string }): void {
    this.layers.push(layer.id);
  }
  getSource(id: string): { setData: ReturnType<typeof vi.fn> } | undefined {
    return this.sources.get(id);
  }
  getZoom(): number {
    return this.zoom;
  }
  getCenter(): { lng: number; lat: number } {
    return this.center;
  }
  flyTo(options: unknown): void {
    this.flights.push(options);
  }
  jumpTo(options: unknown): void {
    this.jumps.push(options);
  }
  setStyle(style: unknown): void {
    this.styles.push(style);
  }
  remove(): void {
    this.removed = true;
  }
}

export class FakeMarker {
  static all: FakeMarker[] = [];
  lngLat: [number, number] = [0, 0];
  removed = false;
  constructor(readonly options: { element: HTMLElement }) {
    FakeMarker.all.push(this);
  }
  setLngLat(at: [number, number]): this {
    this.lngLat = at;
    return this;
  }
  addTo(): this {
    return this;
  }
  remove(): void {
    this.removed = true;
  }
  get element(): HTMLElement {
    return this.options.element;
  }
  static live(): FakeMarker[] {
    return FakeMarker.all.filter((m) => !m.removed);
  }
}

class FakeControl {}

export const fakeEngine = { Map: FakeMap, Marker: FakeMarker, NavigationControl: FakeControl };

export function resetFakes(): void {
  FakeMap.all = [];
  FakeMarker.all = [];
  fakeState.archive = true;
  fakeState.world = false;
  fakeState.engine = true;
}
