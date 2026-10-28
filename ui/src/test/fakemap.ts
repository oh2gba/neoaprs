// A stand-in for MapLibre in the component tests (there is no WebGL in the test browser): it keeps what the page asked of it and lets a test fire the map's events. The component gets it
// through a mock of "@/lib/basemap".
import { vi } from "vitest";

export const fakeState = { archive: true, world: false, engine: true };

type Handler = (event?: unknown) => void;

export class FakeMap {
  static all: FakeMap[] = [];
  handlers = new Map<string, Handler[]>();
  sources = new Map<string, { setData: ReturnType<typeof vi.fn>; data?: unknown }>();
  layers: string[] = [];
  zoom: number;
  center: { lng: number; lat: number };
  flights: unknown[] = [];
  eases: unknown[] = [];
  /** what `fitBounds` was asked: the corners and the options */
  fits: { bounds: [[number, number], [number, number]]; options: Record<string, unknown> }[] = [];
  jumps: unknown[] = [];
  pans: unknown[] = [];
  /** where `project` puts a place, in the pixels of the map; a test sets it */
  screen = { x: 0, y: 0 };
  /** the place `unproject` gives for any pixel of the map; a test sets it */
  place = { lng: 24.94, lat: 60.17 };
  moving = false;
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

  /** `on(event, handler)` or, for a layer, `on(event, layer, handler)`; a test fires the second as `fire(event, payload, layer)`. */
  on(event: string, ...rest: [Handler] | [string, Handler]): this {
    const handler = rest[rest.length - 1] as Handler;
    const key = rest.length === 2 ? `${event}:${rest[0]}` : event;
    this.handlers.set(key, [...(this.handlers.get(key) ?? []), handler]);
    return this;
  }

  fire(event: string, payload?: unknown, layer?: string): void {
    for (const handler of this.handlers.get(layer === undefined ? event : `${event}:${layer}`) ?? []) handler(payload);
  }

  addControl(): void {}
  resizes = 0;
  resize(): void {
    this.resizes += 1;
  }
  addSource(id: string, source?: { data?: unknown }): void {
    this.sources.set(id, { setData: vi.fn(), data: source?.data });
  }
  addLayer(layer: { id: string }): void {
    this.layers.push(layer.id);
  }
  getSource(id: string): { setData: ReturnType<typeof vi.fn>; data?: unknown } | undefined {
    return this.sources.get(id);
  }
  getLayer(id: string): { id: string } | undefined {
    return this.layers.includes(id) ? { id } : undefined;
  }
  /** what `setLayoutProperty` set the visibility of a layer to, by its id */
  visibility = new Map<string, string>();
  setLayoutProperty(id: string, name: string, value: string): void {
    if (name === "visibility") this.visibility.set(id, value);
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
  easeTo(options: unknown): void {
    this.eases.push(options);
  }
  fitBounds(bounds: [[number, number], [number, number]], options: Record<string, unknown> = {}): void {
    this.fits.push({ bounds, options });
  }
  project(): { x: number; y: number } {
    return this.screen;
  }
  unproject(): { lng: number; lat: number } {
    return this.place;
  }
  isMoving(): boolean {
    return this.moving;
  }
  panBy(offset: [number, number], options?: unknown): void {
    this.pans.push({ offset, options });
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
  draggable = false;
  handlers = new Map<string, Handler[]>();
  constructor(readonly options: { element: HTMLElement }) {
    FakeMarker.all.push(this);
  }
  setDraggable(on: boolean): this {
    this.draggable = on;
    return this;
  }
  getLngLat(): { lng: number; lat: number } {
    return { lng: this.lngLat[0], lat: this.lngLat[1] };
  }
  on(event: string, handler: Handler): this {
    this.handlers.set(event, [...(this.handlers.get(event) ?? []), handler]);
    return this;
  }
  /** The user drops the marker at a place: its position moves and `dragend` fires. */
  dragTo(lat: number, lon: number): void {
    this.lngLat = [lon, lat];
    for (const handler of this.handlers.get("dragend") ?? []) handler();
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
