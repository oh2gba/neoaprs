// The types of the catalogues, made from the English one.
import type { en } from "@/i18n/en";
import type { Message } from "@/i18n/message";

/** The id of a message: `area.thing.detail`. */
export type MessageId = keyof typeof en;

/** The catalogue of a language: every id of the English one. */
export type Catalogue = Readonly<Record<MessageId, Message>>;
