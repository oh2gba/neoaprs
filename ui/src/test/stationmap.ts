// The station map mounted for its tests: the props it was given before the page's context existed (`stations`, `home`, `now`, `dark`, `aging` and `filesKey` are the context's now, the others the map's own props), put where they belong,
// and `setProps` of the wrapper sends each of them to the same place, so that a test changes the map's input the way it did.
import { mount, type VueWrapper } from "@vue/test-utils";
import { nextTick } from "vue";
import StationMap from "@/components/StationMap.vue";
import type { MapFileInfo } from "@/protocol/protocol";
import { fakeDaemon, tell, withDaemon, type FakeDaemon } from "@/test/context";
import { mapFile, mapState } from "@/test/fixtures";

const AMBIENT = ["stations", "home", "now", "dark", "aging"] as const;

/** The map state that has the `filesKey` of the old tests: "<detail modified> <world modified>", a dash for a file that is not there. */
function mapOf(key: string | null | undefined) {
  if (key === null || key === undefined) return null;
  const [detail = "-", world = "-"] = key.split(" ");
  const file = (modified: string): MapFileInfo | null => (modified === "-" ? null : mapFile({ modified }));
  return mapState({ detail: file(detail), world: file(world) });
}

export function mountStationMap(props: Record<string, unknown>, attachTo: HTMLElement = document.body): { wrapper: VueWrapper; daemon: FakeDaemon } {
  const { stations, home, now, dark, aging, filesKey, ...own } = props;
  const daemon = fakeDaemon({ stations, home, now, dark, aging, map: mapOf(filesKey as string | null | undefined) } as Parameters<typeof fakeDaemon>[0]);
  const wrapper = mount(StationMap, { props: own as never, global: withDaemon(daemon), attachTo });
  const setProps = wrapper.setProps.bind(wrapper);
  wrapper.setProps = async (next: Record<string, unknown>) => {
    const parts: Record<string, unknown> = {};
    const mine: Record<string, unknown> = {};
    for (const [key, value] of Object.entries(next)) {
      if ((AMBIENT as readonly string[]).includes(key)) parts[key] = value;
      else if (key === "filesKey") parts.map = mapOf(value as string | null);
      else mine[key] = value;
    }
    await tell(daemon, parts);
    await setProps(mine);
    await nextTick();
  };
  return { wrapper, daemon };
}
