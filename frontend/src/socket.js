// The WebSocket connection: envelope constants mirrored from src/contracts/wire.py,
// the two mandatory seq rules, and reconnect-with-backoff.
//
// wire.py's ServerMessage.seq docstring, verbatim: "Monotonic, assigned by exactly one
// counter in `viewer`. Never set by a caller. Client rules, both required:
//   - Gap (seq > last_applied + 1) -> request a full resync. A silently stale viewport
//     is worse than a slow one.
//   - Duplicate or out-of-order (seq <= last_applied) -> ignore. Retries happen, and a
//     client that applies mesh updates additively would otherwise double-apply one."
//
// classifySeq is the pure, directly-tested half of that rule (frontend/tests/socket.test.js).
// SocketClient is the impure half — actual WebSocket wiring — deliberately thin and not
// itself unit-tested, since testing it would mean faking a WebSocket rather than testing
// the decision it delegates to classifySeq.

/** Mirrors contracts.wire.ServerMessageType. Values are the wire strings, not enum names. */
export const ServerMessageType = Object.freeze({
  HELLO: 'hello',
  FULL_SCENE: 'full_scene',
  MESH_UPSERT: 'mesh_upsert',
  TRANSFORM_UPDATE: 'transform_update',
  OBJECTS_REMOVED: 'objects_removed',
  HIGHLIGHT: 'highlight',
  LOG: 'log',
  PHASE: 'phase',
  RUN_STATE: 'run_state',
  PROBLEMS: 'problems',
  CONFLICT: 'conflict',
  EXPORT_REPORT: 'export_report',
  RESYNC_REQUIRED: 'resync_required',
  ERROR: 'error',
});

/** Mirrors contracts.wire.ClientMessageType. */
export const ClientMessageType = Object.freeze({
  PAUSE: 'pause',
  RESUME: 'resume',
  ROLLBACK: 'rollback',
  REDIRECT: 'redirect',
  REQUEST_FULL_SCENE: 'request_full_scene',
  SET_CADENCE: 'set_cadence',
  SELECT: 'select',
});

/** Mirrors contracts.wire.WIRE_VERSION. */
export const WIRE_VERSION = 1;

/**
 * Decide what to do with an incoming ServerMessage.seq, per wire.py's two rules.
 *
 * @param {number|null|undefined} lastApplied the seq of the last message this client
 *   applied, or null/undefined before the first message has ever arrived.
 * @param {number} seq the seq on the message that just arrived.
 * @returns {'apply'|'resync'|'ignore'}
 */
export function classifySeq(lastApplied, seq) {
  if (lastApplied === null || lastApplied === undefined) return 'apply';
  if (seq > lastApplied + 1) return 'resync';
  if (seq <= lastApplied) return 'ignore';
  return 'apply';
}

const INITIAL_BACKOFF_MS = 500;
const MAX_BACKOFF_MS = 10_000;

/**
 * A thin WebSocket wrapper: connects, applies the seq gate, requests a resync on a gap,
 * and reconnects with capped exponential backoff on close/error. Every incoming message
 * is handed to `onMessage` only when classifySeq says 'apply'; a 'resync' verdict sends
 * REQUEST_FULL_SCENE and waits (the next FULL_SCENE that arrives resets the baseline
 * unconditionally, since it is itself the resync payload).
 */
export class SocketClient {
  /**
   * @param {string} url
   * @param {{onMessage: (msg: object) => void, onStatusChange: (status: 'connecting'|'open'|'closed') => void}} handlers
   * @param {{WebSocketImpl?: typeof WebSocket}} [options] inject a WebSocket constructor for
   *   environments where the global is absent; defaults to globalThis.WebSocket.
   */
  constructor(url, handlers, options = {}) {
    this.url = url;
    this.onMessage = handlers.onMessage;
    this.onStatusChange = handlers.onStatusChange ?? (() => {});
    this.WebSocketImpl = options.WebSocketImpl ?? globalThis.WebSocket;
    this.socket = null;
    this.lastApplied = null;
    this.awaitingResync = false;
    this.backoffMs = INITIAL_BACKOFF_MS;
    this.closedByCaller = false;
    this.reconnectTimer = null;
  }

  connect() {
    if (!this.WebSocketImpl) {
      throw new Error('no WebSocket implementation available in this environment');
    }
    this.closedByCaller = false;
    this.onStatusChange('connecting');
    const socket = new this.WebSocketImpl(this.url);
    this.socket = socket;
    socket.addEventListener('open', () => {
      this.backoffMs = INITIAL_BACKOFF_MS;
      this.onStatusChange('open');
    });
    socket.addEventListener('message', (event) => this._handleRawMessage(event.data));
    socket.addEventListener('close', () => this._handleClose());
    socket.addEventListener('error', () => {
      // 'close' always follows 'error' for a browser WebSocket; reconnect lives there.
    });
  }

  send(clientMessage) {
    if (this.socket && this.socket.readyState === this.WebSocketImpl.OPEN) {
      this.socket.send(JSON.stringify(clientMessage));
      return true;
    }
    return false;
  }

  close() {
    this.closedByCaller = true;
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    this.socket?.close();
  }

  _handleRawMessage(raw) {
    let message;
    try {
      message = typeof raw === 'string' ? JSON.parse(raw) : raw;
    } catch {
      return; // malformed frame — drop it rather than crash the socket loop
    }
    this._handleMessage(message);
  }

  _handleMessage(message) {
    if (message.type === ServerMessageType.FULL_SCENE || message.type === ServerMessageType.HELLO) {
      // A full snapshot is authoritative — it IS the resync payload, so it always
      // resets the baseline rather than going through the gap/duplicate gate itself.
      this.lastApplied = message.seq;
      this.awaitingResync = false;
      this.onMessage(message);
      return;
    }

    if (this.awaitingResync) {
      // Ordinary messages are meaningless mid-resync; wait for the FULL_SCENE above.
      return;
    }

    const action = classifySeq(this.lastApplied, message.seq);
    if (action === 'ignore') return;
    if (action === 'resync') {
      this.awaitingResync = true;
      this.send({ type: ClientMessageType.REQUEST_FULL_SCENE, data: {} });
      return;
    }
    this.lastApplied = message.seq;
    this.onMessage(message);
  }

  _handleClose() {
    this.onStatusChange('closed');
    if (this.closedByCaller) return;
    this.reconnectTimer = setTimeout(() => this.connect(), this.backoffMs);
    this.backoffMs = Math.min(this.backoffMs * 2, MAX_BACKOFF_MS);
  }
}
