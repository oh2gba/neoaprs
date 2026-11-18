// The text of the packets' filter (components/PacketsLog.vue): one for the page, so that the Packets tab and the Packets card over the map always show the same list. It lasts as long as the page.
import { ref, type Ref } from "vue";

const filter = ref("");

export const usePacketFilter = (): Ref<string> => filter;
