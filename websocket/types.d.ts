import { IncomingMessage, ServerResponse } from "http";
import type { RawData, WebSocket } from "ws";

export interface Message {
  id: number;
  channel: string;
  message: string;
}

export interface WebSocketExtended extends WebSocket {
  lastMessage: number;
  filter: Record<string, boolean>;
  gotMessage(message: Message): void;
}

export interface IncomingMessageExtended extends IncomingMessage {
  lastMessage: number;
  channels: Record<string, boolean>;
  gotMessage(message: Message): boolean;
}

export interface ServerResponseExtended extends ServerResponse<IncomingMessageExtended> {
  req: IncomingMessageExtended;
}

export type WebSocketRawExtended = RawData & {
  command: string;
  filter: unknown[];
  start: number;
  channel: unknown;
  message: string;
};
