// The station map mounted for its tests: the props given before the page's context existed are put
// where they belong, and `setProps` of the wrapper sends each to the same place.
import { mount, type VueWrapper } from "@vue/test-utils";
import { nextTick } from "vue";
import StationMap from "@/components/StationMap.vue";
import type { MapFileInfo } from "@/protocol/protocol";
import { fakeDaemon, tell, withDaemon, type FakeDaemon } from "@/test/context";
import { mapFile, mapState } from "@/test/fixtures";

const AMBIENT = ["stations", "home", "now", "dark", "aging", "gps"] as const;

/** The map state with the `filesKey` of the old tests: "<detail modified> <world modified>". */
function mapOf(key: string | null | undefined) {
  if (key === null || key === undefined) return null;
  const [detail = "-", world = "-"] = key.split(" ");
  const file = (modified: string): MapFileInfo | null => (modified === "-" ? null : mapFile({ modified }));
  return mapState({ detail: file(detail), world: file(world) });
}

export function mountStationMap(props: Record<string, unknown>, attachTo: HTMLElement = document.body): { wrapper: VueWrapper; daemon: FakeDaemon } {
  const { stations, home, now, dark, aging, gps, filesKey, ...own } = props;
  const daemon = fakeDaemon({ stations, home, now, dark, aging, gps, map: mapOf(filesKey as string | null | undefined) } as Parameters<typeof fakeDaemon>[0]);
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
