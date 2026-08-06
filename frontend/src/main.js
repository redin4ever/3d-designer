// Entry point: wires the socket, the viewport, the action log and the controls panel
// together. Nothing exported — this is the one file allowed to reach into the DOM
// directly at the top level, per frontend/CLAUDE.md's module boundaries.
//
// frontend depends only on src/contracts/wire.py (ARCHITECTURE.md) — not on src/viewer's
// current implementation, which is free to still be a stub. The default WebSocket target
// below (ws://127.0.0.1:8766, no path) matches src/viewer/server.py's `serve()` defaults,
// which is the best evidence available for where a real backend will listen, but it is a
// default, not a contract — override it with `?ws=` for any other target.

import { SocketClient, ServerMessageType, ClientMessageType } from './socket.js';
import {
  createViewportState,
  applyMeshUpsert,
  applyTransformUpdate,
  applyObjectsRemoved,
  applyHighlight,
  clearViewportState,
} from './viewport.js';
import { SceneRenderer } from './scene-renderer.js';
import { createActionLog, appendLogEntry, renderActionLog } from './log.js';
import {
  createTranscript,
  appendOperatorMessage,
  applyServerLog,
  markPendingUnconfirmed,
  renderTranscript,
} from './transcript.js';
import { attachControls, buildRequestFullSceneMessage } from './controls.js';
import { attachConnectButton } from './connect-ui.js';

function resolveSocketUrl() {
  const override = new URLSearchParams(location.search).get('ws');
  if (override) return override;
  return 'ws://127.0.0.1:8766';
}

function main() {
  const canvas = document.getElementById('viewport-canvas');
  const banner = document.getElementById('connection-banner');
  const bannerDetail = document.getElementById('connection-banner-detail');
  const statusPill = document.getElementById('connection-status');
  const logList = document.getElementById('action-log');
  const transcriptList = document.getElementById('chat-transcript');
  // The whole layout, not just .controls-panel: the redirect composer sits in the
  // conversation panel now, so the run controls and the composer are in different
  // sections and attachControls has to be able to see both.
  const controlsRoot = document.querySelector('.layout');
  const controlError = document.getElementById('control-error');

  const renderer = new SceneRenderer(canvas);
  const viewportState = createViewportState();
  const actionLog = createActionLog();
  const transcript = createTranscript();

  renderer.start();

  const pushLog = (text, kind) => {
    appendLogEntry(actionLog, { text, kind, at: Date.now() });
    renderActionLog(actionLog, logList);
  };

  /** A conversation line. `message` is a wire LOG, or a local status line with no seq. */
  const pushTranscript = (message) => {
    applyServerLog(transcript, message);
    renderTranscript(transcript, transcriptList);
  };

  const setStatus = (status, detail) => {
    statusPill.dataset.status = status;
    statusPill.textContent =
      status === 'open' ? 'Connected' : status === 'connecting' ? 'Connecting…' : 'Not connected';
    banner.hidden = status === 'open';
    if (detail) bannerDetail.textContent = detail;
  };

  const socket = new SocketClient(
    resolveSocketUrl(),
    {
      onStatusChange: (status) => {
        setStatus(
          status,
          status === 'closed'
            ? 'Lost the connection. Retrying automatically — this page will pick the build back up, no reload needed.'
            : status === 'connecting'
              ? 'Waiting for a build to connect.'
              : undefined,
        );
        if (status === 'open') {
          pushLog('connected', 'status');
          pushTranscript({ text: 'connected', data: { role: 'system' } });
        }
        if (status === 'closed') {
          pushLog('disconnected — retrying', 'status');
          // Nothing still in flight can be confirmed across a dropped socket. Leaving
          // those lines looking pending would have the operator waiting on an echo that
          // is never coming.
          markPendingUnconfirmed(transcript);
          pushTranscript({ text: 'disconnected — retrying', data: { role: 'system' } });
        }
      },
      onMessage: (message) => handleServerMessage(message),
    },
  );

  function handleServerMessage(message) {
    switch (message.type) {
      case ServerMessageType.HELLO:
        pushLog(`hello — wire v${message.data?.wire_version ?? '?'}`, 'status');
        break;
      case ServerMessageType.FULL_SCENE:
        clearViewportState(viewportState, renderer);
        applyMeshUpsert(viewportState, { meshes: message.meshes }, renderer);
        applyTransformUpdate(viewportState, { transforms: message.transforms }, renderer);
        pushLog(`full scene — ${message.meshes?.length ?? 0} objects`, 'status');
        break;
      case ServerMessageType.MESH_UPSERT:
        applyMeshUpsert(viewportState, message, renderer);
        // The server sends `transforms` alongside `meshes` on every MESH_UPSERT
        // (src/viewer/translate.py builds both from the same snapshot), and
        // applyMeshUpsert creates each node at the identity transform. Without this
        // second call every new object rendered at the world origin, and an object that
        // had been positioned by an earlier TRANSFORM_UPDATE snapped back there the
        // moment its topology changed — silently, with nothing logged. FULL_SCENE above
        // always did both; this case did not.
        applyTransformUpdate(viewportState, { transforms: message.transforms }, renderer);
        break;
      case ServerMessageType.TRANSFORM_UPDATE:
        applyTransformUpdate(viewportState, message, renderer);
        break;
      case ServerMessageType.OBJECTS_REMOVED:
        applyObjectsRemoved(viewportState, message, renderer);
        break;
      case ServerMessageType.HIGHLIGHT:
        applyHighlight(viewportState, message, renderer);
        pushLog(`changed: ${(message.object_ids ?? []).join(', ') || '(none)'}`, 'highlight');
        break;
      case ServerMessageType.LOG:
        // Every LOG is conversation; only system-role ones are also machine record. An
        // agent's reply duplicated into the action log is noise, but a role-less LOG from
        // an older backend has to keep landing in the log exactly as it always did.
        pushTranscript(message);
        if (!message.data?.role || message.data.role === 'system') pushLog(message.text, 'log');
        break;
      case ServerMessageType.PHASE:
        pushLog(`phase → ${message.text}`, 'status');
        break;
      case ServerMessageType.RUN_STATE:
        pushLog(`run state → ${message.text}`, 'status');
        break;
      case ServerMessageType.PROBLEMS:
        pushLog(`problems: ${message.text || JSON.stringify(message.data ?? {})}`, 'log');
        break;
      case ServerMessageType.CONFLICT:
        pushLog(`conflict: ${message.text}`, 'error');
        break;
      case ServerMessageType.EXPORT_REPORT:
        pushLog(`export: ${message.text}`, 'log');
        break;
      case ServerMessageType.RESYNC_REQUIRED:
        clearViewportState(viewportState, renderer);
        socket.send(buildRequestFullSceneMessage());
        pushLog('resync required — requesting full scene', 'status');
        break;
      case ServerMessageType.ERROR:
        pushLog(`error: ${message.text}`, 'error');
        break;
      default:
        pushLog(`unhandled message: ${message.type}`, 'log');
    }
  }

  attachControls(controlsRoot, {
    send: (clientMessage) => {
      // Show the operator's own words the instant they press Enter. The server echoes
      // them back once it has queued them, and that echo is what turns this line from
      // "sending…" into "queued for the agent" — reconciled, not printed twice.
      if (clientMessage.type === ClientMessageType.REDIRECT) {
        appendOperatorMessage(transcript, clientMessage.data.text);
        renderTranscript(transcript, transcriptList);
      }
      const sent = socket.send(clientMessage);
      if (!sent) {
        pushLog(`not connected — "${clientMessage.type}" was not sent`, 'error');
        markPendingUnconfirmed(transcript);
        renderTranscript(transcript, transcriptList);
      }
      controlError.textContent = '';
      // controls.js keeps the composer's text when this is false, so nothing typed is
      // thrown away by a send that never left the browser.
      return sent;
    },
    onError: (message) => {
      controlError.textContent = message;
    },
  });

  // `document`, not `.layout`: the client picker is a <dialog> that renders in the top
  // layer and lives outside <main>, so a root scoped to the layout cannot see it. Nothing
  // here touches the socket — connecting an AI client is a one-off setup action against the
  // page's own HTTP origin, and it is deliberately not on the wire protocol.
  attachConnectButton(document);

  setStatus('connecting');
  socket.connect();

  window.addEventListener('beforeunload', () => socket.close());
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', main);
} else {
  main();
}
