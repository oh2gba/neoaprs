// A WebSocket the tests drive by hand: what the page sends is kept, what the daemon says is `say`.
// A `set_config` is kept without its number, which stays in `asked` until the daemon says the settings
// (it then says `saved`, as the daemon does) or refuses it with an `error`.
import type { SocketLike } from "@/lib/hub";

export class FakeSocket implements SocketLike {
  static all: FakeSocket[] = [];
  onopen: ((event: Event) => void) | null = null;
  onmessage: ((event: MessageEvent) => void) | null = null;
  onclose: ((event: CloseEvent) => void) | null = null;
  onerror: ((event: Event) => void) | null = null;
  binaryType = "blob";
  sent: unknown[] = [];
  closed = false;
  asked: number[] = [];

  constructor(readonly url: string) {
    FakeSocket.all.push(this);
  }

  send(data: string): void {
    const command = JSON.parse(data) as { cmd?: string; id?: number };
    if (command.cmd === "set_config" && typeof command.id === "number") {
      this.asked.push(command.id);
      delete command.id;
    }
    this.sent.push(command);
  }

  close(): void {
    this.closed = true;
  }

  sayBytes(bytes: Uint8Array): void {
    this.onmessage?.(
      new MessageEvent("message", { data: bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength) }),
    );
  }

  say(message: object): void {
    this.onmessage?.(new MessageEvent("message", { data: JSON.stringify(message) }));
    const said = message as { type?: string; topic?: string; cmd?: string; id?: number };
    if (said.type === "error" && said.cmd === "set_config" && said.id === undefined) this.asked.shift();
    if ((said.type === "state" || said.type === "patch") && said.topic === "config" && this.asked.length > 0)
      this.say({ type: "saved", id: this.asked.shift() });
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
