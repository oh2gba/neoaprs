import { afterEach, describe, expect, it } from "vitest";
import { effectScope, nextTick, ref, type Ref } from "vue";
import { useCardDrag, type Places } from "@/composables/useCardDrag";

function stackOf(wrap: HTMLElement): HTMLElement {
  const stack = document.createElement("div");
  stack.innerHTML = '<div class="card" data-call="A"><div class="card-head"><span class="h">A</span></div></div>';
  wrap.append(stack);
  return stack;
}

function pointer(type: string, x: number, y: number, target: Element, id = 1): PointerEvent {
  const event = new MouseEvent(type, { clientX: x, clientY: y, bubbles: true, button: 0 }) as unknown as PointerEvent;
  Object.defineProperty(event, "pointerId", { value: id });
  Object.defineProperty(event, "target", { value: target });
  return event;
}

function setUp() {
  const wrap = document.createElement("div");
  wrap.className = "mapwrap";
  document.body.append(wrap);
  const stack: Ref<HTMLElement | null> = ref(stackOf(wrap));
  const places: Ref<Places> = ref({});
  const scope = effectScope();
  const drag = scope.run(() => useCardDrag(stack, places, () => true));
  if (drag === undefined) throw new Error("no scope");
  const head = (): Element => stack.value?.querySelector(".h") ?? document.body;
  return { wrap, stack, places, drag, scope, head };
}

afterEach(() => {
  document.body.classList.remove("card-dragging");
  document.body.replaceChildren();
});

describe("a card drag whose card goes away under the pointer", () => {
  it("is given up, and a new press on a new card drags it", () => {
    const { wrap, stack, drag, scope, head } = setUp();
    drag.down(pointer("pointerdown", 10, 10, head()));
    drag.move(pointer("pointermove", 40, 40, head()));
    expect(document.body.classList.contains("card-dragging")).toBe(true);
    stack.value?.remove(); // (Esc closed the cards while the button was held: no pointerup reaches the stack)
    stack.value = stackOf(wrap);
    drag.down(pointer("pointerdown", 10, 10, head(), 2));
    expect(document.body.classList.contains("card-dragging")).toBe(false);
    drag.move(pointer("pointermove", 90, 90, head(), 2));
    expect(document.body.classList.contains("card-dragging"), "the new press is a drag").toBe(true);
    scope.stop();
  });

  it("is given up when the stack is gone", async () => {
    const { stack, drag, scope, head } = setUp();
    drag.down(pointer("pointerdown", 10, 10, head()));
    drag.move(pointer("pointermove", 40, 40, head()));
    stack.value = null;
    await nextTick();
    expect(document.body.classList.contains("card-dragging")).toBe(false);
    scope.stop();
  });
});
