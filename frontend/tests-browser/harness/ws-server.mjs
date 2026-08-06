// A minimal RFC 6455 server that speaks src/contracts/wire.py's envelope.
//
// Hand-rolled rather than pulling in `ws`, for the same reason the frontend has no
// three.js: this workspace adds no runtime or test dependency it does not have to
// (ADR-008, ADR-016). Text frames only, no fragmentation, no permessage-deflate — the
// browser sends short unfragmented text frames for every ClientMessage the controls
// panel can produce, so that is the whole surface this needs to cover.
//
// It stands in for src/viewer/server.py::_handle_connection: greet with HELLO, push a
// FULL_SCENE, then answer whatever the client sends. Feeding the page canned wire
// messages this way is what the brief permits in place of standing up Blender.

import { createServer } from 'node:http';
import { createHash } from 'node:crypto';

const WS_GUID = '258EAFA5-E914-47DA-95CA-5AB0DC85B39A';
const OP_TEXT = 0x1;
const OP_CLOSE = 0x8;
const OP_PING = 0x9;
const OP_PONG = 0xa;

const acceptKey = (key) => createHash('sha1').update(key + WS_GUID).digest('base64');

function frame(payloadText, opcode = OP_TEXT) {
  const payload = Buffer.from(payloadText, 'utf8');
  const n = payload.length;
  let head;
  if (n < 126) {
    head = Buffer.from([0x80 | opcode, n]);
  } else if (n < 65536) {
    head = Buffer.alloc(4);
    head[0] = 0x80 | opcode;
    head[1] = 126;
    head.writeUInt16BE(n, 2);
  } else {
    head = Buffer.alloc(10);
    head[0] = 0x80 | opcode;
    head[1] = 127;
    head.writeBigUInt64BE(BigInt(n), 2);
  }
  return Buffer.concat([head, payload]);
}

/** Pull every complete frame out of `state.buf`, unmasking client→server payloads. */
function* readFrames(state) {
  for (;;) {
    const buf = state.buf;
    if (buf.length < 2) return;
    const opcode = buf[0] & 0x0f;
    const masked = (buf[1] & 0x80) !== 0;
    let len = buf[1] & 0x7f;
    let at = 2;
    if (len === 126) {
      if (buf.length < 4) return;
      len = buf.readUInt16BE(2);
      at = 4;
    } else if (len === 127) {
      if (buf.length < 10) return;
      len = Number(buf.readBigUInt64BE(2));
      at = 10;
    }
    let mask = null;
    if (masked) {
      if (buf.length < at + 4) return;
      mask = buf.subarray(at, at + 4);
      at += 4;
    }
    if (buf.length < at + len) return;
    const payload = Buffer.from(buf.subarray(at, at + len));
    if (mask) for (let i = 0; i < payload.length; i += 1) payload[i] ^= mask[i % 4];
    state.buf = buf.subarray(at + len);
    yield { opcode, payload };
  }
}

/**
 * @param {{greeting?: object[], onClientMessage?: (msg: object) => object[]|undefined}} options
 *   `greeting` is pushed to every client the moment it connects, in order.
 * @returns {Promise<{url: string, received: object[], broadcast: (msg: object) => void,
 *   close: () => Promise<void>}>}
 */
export async function startWireServer({ greeting = [], onClientMessage } = {}) {
  /** @type {object[]} every ClientMessage the page sent, in arrival order */
  const received = [];
  const live = new Set();

  const server = createServer((_req, res) => {
    res.writeHead(426, { 'content-type': 'text/plain' });
    res.end('this endpoint speaks websocket only');
  });

  server.on('upgrade', (req, socket) => {
    const key = req.headers['sec-websocket-key'];
    if (!key) {
      socket.destroy();
      return;
    }
    socket.write(
      [
        'HTTP/1.1 101 Switching Protocols',
        'Upgrade: websocket',
        'Connection: Upgrade',
        `Sec-WebSocket-Accept: ${acceptKey(key)}`,
        '',
        '',
      ].join('\r\n'),
    );
    live.add(socket);
    socket.on('close', () => live.delete(socket));
    socket.on('error', () => live.delete(socket));

    const state = { buf: Buffer.alloc(0) };
    socket.on('data', (chunk) => {
      state.buf = Buffer.concat([state.buf, chunk]);
      for (const { opcode, payload } of readFrames(state)) {
        if (opcode === OP_CLOSE) {
          socket.end(frame('', OP_CLOSE));
          return;
        }
        if (opcode === OP_PING) {
          socket.write(frame(payload.toString('utf8'), OP_PONG));
          continue;
        }
        if (opcode !== OP_TEXT) continue;
        let message;
        try {
          message = JSON.parse(payload.toString('utf8'));
        } catch {
          continue;
        }
        received.push(message);
        for (const out of onClientMessage?.(message) ?? []) {
          socket.write(frame(JSON.stringify(out)));
        }
      }
    });

    for (const message of greeting) socket.write(frame(JSON.stringify(message)));
  });

  await new Promise((done) => server.listen(0, '127.0.0.1', done));
  const { port } = server.address();

  return {
    url: `ws://127.0.0.1:${port}`,
    received,
    broadcast(message) {
      const encoded = frame(JSON.stringify(message));
      for (const socket of live) socket.write(encoded);
    },
    async close() {
      for (const socket of live) socket.destroy();
      await new Promise((done) => server.close(done));
    },
  };
}
