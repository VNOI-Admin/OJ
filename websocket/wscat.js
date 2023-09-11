#!/usr/bin/env node
// @ts-check

/*!
 * ws: a node.js websocket client
 * Copyright(c) 2011 Einar Otto Stangvik <einaros@gmail.com>
 * MIT Licensed
 */

/**
 * Module dependencies.
 */
import { Command } from "@commander-js/extra-typings";
import events from "events";
import readline from "readline";
import { WebSocket, WebSocketServer } from "ws";

/**
 * InputReader - processes console input
 */
class Console extends events.EventEmitter {
  static colors = /** @type {const} */ ({
    red: "\x1b[31m",
    green: "\x1b[32m",
    yellow: "\x1b[33m",
    cyan: "\x1b[36m",
    blue: "\x1b[34m",
    default: "\x1b[39m",
  });
  constructor() {
    super();
    /**
     * Console's readline interface.
     * @type {readline.Interface}
     * @public
     */
    this.readlineInterface = readline.createInterface(process.stdin, process.stdout);

    this.readlineInterface.on("line", (data) => {
      this.emit("line", data);
    });

    this.readlineInterface.on("close", () => {
      this.emit("close");
    });
  }
  /**
   * Wrapper of readline interface's prompt.
   */
  prompt() {
    this.readlineInterface.prompt();
  }
  /**
   * Clears stdout.
   */
  clear() {
    process.stdout.write("\x1b[2K\x1b[E");
  }
  /**
   * Clears stdout, then prints message with color.
   * @param {string} message
   * @param {string} [color]
   */
  print(message, color = Console.colors.default) {
    this.clear();
    process.stdout.write(`${color}${message}${Console.colors.default}\n`);
    this.prompt();
  }
  /**
   * Pauses stdin.
   */
  pause() {
    process.stdin.on("keypress", this.clear);
  }
  /**
   * Clears stdin.
   */
  resume() {
    process.stdin.removeListener("keypress", this.clear);
  }
}

/**
 * Creates a function that pushs an element to an array, then returns that array
 * immediately.
 * @template T
 * @param {T[]} xs
 * @returns
 */
const appender = (xs = []) => {
  /**
   * @param {T} x
   */
  return (x) => {
    xs.push(x);
    return xs;
  };
};

/**
 * Assigns keys to its corresponding values on an object and returns it.
 * @param {Record<string, string>} obj
 * @param {[string, string][]} kvals
 * @returns
 */
function into(obj, kvals) {
  kvals.forEach((kv) => {
    obj[kv[0]] = kv[1];
  });
  return obj;
}

/**
 * Splits a string by a separator once.
 * @param {string | RegExp} sep
 * @param {string} str
 * @returns {[string, string]}
 */
const splitOnce = (sep, str) => {
  const tokens = str.split(sep);
  return [tokens[0], str.replace(sep, "").substring(tokens[0].length)];
};

/**
 * The actual application
 */
const version = "1.0"; //JSON.parse(fs.readFileSync(__dirname + '/../package.json', 'utf8')).version;
const program = new Command()
  .version(version)
  .usage("[options] <url>")
  .option("-l, --listen <port>", "Listen on port")
  .option("-c, --connect <url>", "Connect to a websocket server")
  .option("-p, --protocol <version>", "Specify an optional protocol version (--connect only)")
  .option("-o, --origin <origin>", "Specify an optional origin (--connect only)")
  .option("--host <host>", "Specify an optional host")
  .option("-s, --subprotocol <protocol>", "optional subprotocol (--connect only)")
  .option("-n, --no-check", "Do not check for unauthorized certificates (--connect only)")
  .option(
    "-H, --header <header:value>",
    "Set an HTTP header. Repeat to set multiple. (--connect only)",
    appender(),
    [],
  )
  .option("--auth <username:password>", "Add basic HTTP authentication header. (--connect only)")
  .parse(process.argv);

const programOptions = program.opts();

if (programOptions.listen && programOptions.connect) {
  console.error("\x1b[33merror: use either --listen or --connect\x1b[39m");
  process.exit(-1);
} else if (programOptions.listen) {
  const wsConsole = new Console();
  wsConsole.pause();
  const { host } = programOptions;
  /**
   * @type {import("ws").WebSocket | null}
   */
  let ws = null;
  const wss = new WebSocketServer({ port: +programOptions.listen, host }, () => {
    wsConsole.print(
      `listening on port ${programOptions.listen} (press Ctrl+C to quit)`,
      Console.colors.green,
    );
    wsConsole.clear();
  });
  wsConsole.on("close", function () {
    if (ws) {
      try {
        ws.close();
      } catch (e) {}
    }
    process.exit(0);
  });
  wsConsole.on("line", (data) => {
    if (ws) {
      ws.send(data, { mask: false });
      wsConsole.prompt();
    }
  });
  wss.on("connection", (newClient) => {
    if (ws) {
      // limit to one client
      newClient.terminate();
      return;
    }
    ws = newClient;
    wsConsole.resume();
    wsConsole.prompt();
    wsConsole.print("client connected", Console.colors.green);
    ws.on("close", () => {
      wsConsole.print("disconnected", Console.colors.green);
      wsConsole.clear();
      wsConsole.pause();
      ws = null;
    });
    ws.on("error", (code, description) => {
      wsConsole.print(
        `error: ${code} ${description ? ` ${description}` : ""}`,
        Console.colors.yellow,
      );
    });
    ws.on("message", (data) => {
      wsConsole.print(`< ${data}`, Console.colors.blue);
    });
  });
  wss.on("error", function (error) {
    wsConsole.print(`error: ${error.toString()}`, Console.colors.yellow);
    process.exit(-1);
  });
} else if (programOptions.connect) {
  const wsConsole = new Console();
  const {
    protocol,
    origin,
    subprotocol,
    host,
    check: rejectUnauthorized,
    header,
    auth,
  } = programOptions;
  const headers = into(
    {},
    (header || []).map((s) => splitOnce(":", s)),
  );
  if (auth) {
    headers["Authorization"] = `Basic ${Buffer.from(auth).toString("base64")}`;
  }
  const ws = new WebSocket(programOptions.connect, {
    protocolVersion: protocol ? +protocol : undefined,
    origin,
    protocol: subprotocol,
    host,
    rejectUnauthorized,
    headers,
  });
  ws.on("open", () => {
    wsConsole.print("connected (press CTRL+C to quit)", Console.colors.green);
    wsConsole.on("line", (data) => {
      ws.send(data, { mask: true });
      wsConsole.prompt();
    });
  });
  ws.on("close", () => {
    wsConsole.print("disconnected", Console.colors.green);
    wsConsole.clear();
    process.exit();
  });
  ws.on("error", (code, description) => {
    wsConsole.print(
      "error: " + code + (description ? " " + description : ""),
      Console.colors.yellow,
    );
    process.exit(-1);
  });
  ws.on("message", (data) => {
    wsConsole.print("< " + data, Console.colors.cyan);
  });
  wsConsole.on("close", () => {
    if (ws) {
      try {
        ws.close();
      } catch (e) {}
      process.exit();
    }
  });
} else {
  console.error("\x1b[33merror: use either --listen or --connect\x1b[39m");
  process.exit(-1);
}
