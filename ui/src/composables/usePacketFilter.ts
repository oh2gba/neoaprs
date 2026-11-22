// The packets filter text, one for the page so that the Packets tab and card show the same list.
import { ref, type Ref } from "vue";

const filter = ref("");

export const usePacketFilter = (): Ref<string> => filter;
