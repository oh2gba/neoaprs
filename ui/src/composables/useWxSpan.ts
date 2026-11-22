// The span of the weather graphs (24 hours or 7 days, remembered), shared by every open card: the
// station cards provide it so they share the time axis; a card on its own has the remembered value.
import { inject, provide, type InjectionKey, type Ref } from "vue";
import { usePersisted } from "@/composables/usePersisted";

const WX_SPANS = ["24", "168"] as const;
export type WxSpan = (typeof WX_SPANS)[number];
const KEY: InjectionKey<Ref<WxSpan>> = Symbol("wxSpan");

export function provideWxSpan(): Ref<WxSpan> {
  const span = usePersisted("wxhours", "24", WX_SPANS);
  provide(KEY, span);
  return span;
}

export function useWxSpan(): Ref<WxSpan> {
  return inject(KEY, null) ?? usePersisted("wxhours", "24", WX_SPANS);
}
