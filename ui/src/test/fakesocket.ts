// A WebSocket the tests drive by hand: what the page sends is kept, what the daemon says is `say`.
import type { SocketLike } from "@/lib/hub";

export class FakeSocket implements SocketLike {
  static all: FakeSocket[] = [];
  onopen: ((event: Event) => void) | null = null;
  onmessage: ((event: MessageEvent) => void) | null = null;
  onclose: ((event: CloseEvent) => void) | null = null;
  onerror: ((event: Event) => void) | null = null;
  sent: unknown[] = [];
  closed = false;

  constructor(readonly url: string) {
    FakeSocket.all.push(this);
  }

  send(data: string): void {
    this.sent.push(JSON.parse(data));
  }

  close(): void {
    this.closed = true;
  }

  say(message: object): void {
    this.onmessage?.(new MessageEvent("message", { data: JSON.stringify(message) }));
  }

  hangUp(): void {
    this.onclose?.(new CloseEvent("close"));
  }

  static last(): FakeSocket {
    const socket = FakeSocket.all[FakeSocket.all.length - 1];
    if (!socket) throw new Error("no socket was opened");
    return socket;
  }
}
