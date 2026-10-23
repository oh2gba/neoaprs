// The span of the weather graphs (24 hours or 7 days, remembered), one for every card that is open: the station cards provide it (components/StationCards.vue), so that the cards share the time axis and the switch of one is the switch of all; a card on its own (a test, a page that
// has none to provide) has the remembered value of its own.
import { inject, provide, type InjectionKey, type Ref } from "vue";
import { usePersisted } from "@/composables/usePersisted";

const WX_SPANS = ["24", "168"] as const;
export type WxSpan = (typeof WX_SPANS)[number];
const KEY: InjectionKey<Ref<WxSpan>> = Symbol("wxSpan");

/** For the cards' parent: the span, given to every weather panel under it. */
export function provideWxSpan(): Ref<WxSpan> {
  const span = usePersisted("wxhours", "24", WX_SPANS);
  provide(KEY, span);
  return span;
}

/** For a weather panel: the span its parent provides, else the remembered one. */
export function useWxSpan(): Ref<WxSpan> {
  return inject(KEY, null) ?? usePersisted("wxhours", "24", WX_SPANS);
}
