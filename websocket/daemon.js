// @ts-check
/**
 * @typedef {import("./types.js").Message} Message
 * @typedef {import("./types.js").WebSocketExtended} WebSocketExtended
 * @typedef {import("./types.js").IncomingMessageExtended} IncomingMessageExtended
 * @typedef {import("./types.js").ServerResponseExtended} ServerResponseExtended
 * @typedef {import("./types.js").WebSocketRawExtended} WebSocketRawExtended
 */
import { createServer } from "http";
import { WebSocketServer } from "ws";

import config from "./config.js";
import { Queue } from "./queue.js";

const wssReceiver = new WebSocketServer({
  host: config.get_host,
  port: config.get_port,
});
const wssSender = new WebSocketServer({
  host: config.post_host,
  port: config.post_port,
});

/**
 * @type {Queue<Message>}
 */
const messages = new Queue();
/**
 * @type {Set<WebSocketExtended>}
 */
const followers = new Set();
/**
 * @type {Set<IncomingMessageExtended>}
 */
const pollers = new Set();
const maxQueue = config.max_queue || 50;
const maxFilter = config.max_filter || 5;
const maxBodySize = config.max_body_size || 200;
const longPollTimeout = config.long_poll_timeout || 60000;
let messageId = Date.now();

/**
 * @param {WebSocketExtended} client
 */
const messagesCatchUp = (client) => {
  messages.forEach((message) => {
    if (message.id > client.lastMessage) {
      client.gotMessage(message);
    }
  });
};

/**
 * Post a message.
 * @param {string} channel
 * @param {string} message
 * @returns
 */
const messagesPost = (channel, message) => {
  /**
   * @type {Message}
   */
  const resolvedMessage = {
    id: ++messageId,
    channel: channel,
    message: message,
  };
  messages.push(resolvedMessage);
  if (messages.length > maxQueue) {
    messages.pop();
  }
  followers.forEach((client) => {
    client.gotMessage(resolvedMessage);
  });
  pollers.forEach((request) => {
    request.gotMessage(resolvedMessage);
  });
  return resolvedMessage.id;
};

wssReceiver.on("connection", (/** @type {WebSocketExtended} */ socket) => {
  socket.lastMessage = 0;
  const commands = {
    /**
     * @param {WebSocketRawExtended} request
     */
    start_msg(request) {
      try {
        socket.lastMessage = Number(request.start);
      } catch (err) {
        socket.send(
          JSON.stringify({
            status: "error",
            code: "syntax-error",
            message: "syntax error",
          }),
        );
      }
    },
    /**
     * @param {WebSocketRawExtended} request
     */
    set_filter(request) {
      /**
       * @type {Record<string, boolean>}
       */
      try {
        const filter = {};
        if (
          Array.isArray(request.filter) &&
          request.filter.length > 0 &&
          request.filter.length <= maxFilter &&
          request.filter.every((channel) => {
            if (typeof channel !== "string") {
              return false;
            }
            filter[channel] = true;
            return true;
          })
        ) {
          socket.filter = filter;
          followers.add(socket);
          messagesCatchUp(socket);
        } else {
          throw new Error("invalid filter");
        }
      } catch (err) {
        socket.send(
          JSON.stringify({
            status: "error",
            code: "invalid-filter",
            message: "invalid filter",
          }),
        );
      }
    },
  };

  socket.gotMessage = (message) => {
    if (message.channel in socket.filter) {
      socket.send(JSON.stringify(message));
    }
    socket.lastMessage = message.id;
  };

  socket.on("message", (/** @type {WebSocketRawExtended}*/ request) => {
    try {
      request = request.toString();
      if (request.length > maxBodySize) {
        throw new Error("request entity too large");
      }
      request = JSON.parse(request.toString());
      request.command = request.command.replace(/-/g, "_");
      if (request.command in commands) {
        commands[request.command](request);
      } else {
        throw new Error("bad command");
      }
    } catch (err) {
      socket.send(
        JSON.stringify({
          status: "error",
          code: "syntax-error",
          message: "syntax error",
        }),
      );
      return;
    }
  });

  socket.on("close", () => {
    followers.delete(socket);
  });
});

wssSender.on("connection", (socket) => {
  const commands = {
    /**
     * @param {WebSocketRawExtended} request
     * @returns
     */
    post(request) {
      if (typeof request.channel !== "string") {
        return {
          status: "error",
          code: "invalid-channel",
        };
      }
      return {
        status: "success",
        id: messagesPost(request.channel, request.message),
      };
    },
    last_msg() {
      return {
        status: "success",
        id: messageId,
      };
    },
  };
  socket.on("message", (/** @type {WebSocketRawExtended}*/ request) => {
    try {
      request = JSON.parse(request.toString());
    } catch (err) {
      return socket.send(
        JSON.stringify({
          status: "error",
          code: "syntax-error",
          message: err.message,
        }),
      );
    }
    request.command = request.command.replace(/-/g, "_");
    if (request.command in commands) {
      socket.send(JSON.stringify(commands[request.command](request)));
    } else {
      socket.send(
        JSON.stringify({
          status: "error",
          code: "bad-command",
          message: "bad command: " + request.command,
        }),
      );
    }
  });
});

createServer(
  // @ts-expect-error We can't pass generics to `createServer`.
  (/** @type {IncomingMessageExtended} */ req, /** @type {ServerResponseExtended} */ res) => {
    const parts = req.url ? new URL(req.url, "http://n") : undefined;

    if (!parts?.pathname.startsWith("/channels/")) {
      res.writeHead(404, { "Content-Type": "text/plain" });
      res.end("404 Not Found");
      return;
    }

    const channels = decodeURI(parts.pathname).slice(10).split("|");
    if (channels.length == 1 && !channels[0].length) {
      res.writeHead(400, { "Content-Type": "text/plain" });
      res.end("400 Bad Request");
      return;
    }

    req.channels = {};
    req.lastMessage = parseInt(parts.searchParams.get("last") || "0");
    if (isNaN(req.lastMessage)) {
      req.lastMessage = 0;
    }

    channels.forEach((channel) => {
      req.channels[channel] = true;
    });

    req.on("close", () => {
      pollers.delete(req);
    });

    req.gotMessage = (message) => {
      if (message.channel in req.channels) {
        res.writeHead(200, { "Content-Type": "application/json" });
        res.end(JSON.stringify(message));
        pollers.delete(req);
        return true;
      }
      return false;
    };
    let got = false;
    messages.forEach((message) => {
      if (!got && message.id > req.lastMessage) {
        got = req.gotMessage(message);
      }
    });
    if (!got) {
      pollers.add(req);
      res.setTimeout(longPollTimeout, () => {
        pollers.delete(req);
        res.writeHead(504, { "Content-Type": "application/json" });
        res.end('{"error": "timeout"}');
      });
    }
  },
).listen(config.http_port, config.http_host, () => {
  console.log(`Websocket daemon listening on http://${config.http_host}:${config.http_port}`);
});
