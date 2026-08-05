// Entry point: wires the socket, the viewport, the action log and the controls panel
// together. Nothing exported — this is the one file allowed to reach into the DOM
// directly at the top level, per frontend/CLAUDE.md's module boundaries.
//
// frontend depends only on src/contracts/wire.py (ARCHITECTURE.md) — not on src/viewer's
// current implementation, which is free to still be a stub. The default WebSocket target
// below (ws://127.0.0.1:8766, no path) matches src/viewer/server.py's `serve()` defaults,
// which is the best evidence available for where a real backend will listen, but it is a
// default, not a contract — override it with `?ws=` for any other target.

import { SocketClient, ServerMessageType } from './socket.js';
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
import { attachControls, buildRequestFullSceneMessage } from './controls.js';

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
  const controlsRoot = document.querySelector('.controls-panel');
  const controlError = document.getElementById('control-error');

  const renderer = new SceneRenderer(canvas);
  const viewportState = createViewportState();
  const actionLog = createActionLog();

  renderer.start();

  const pushLog = (text, kind) => {
    appendLogEntry(actionLog, { text, kind, at: Date.now() });
    renderActionLog(actionLog, logList);
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
        if (status === 'open') pushLog('connected', 'status');
        if (status === 'closed') pushLog('disconnected — retrying', 'status');
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
        pushLog(message.text, 'log');
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
      const sent = socket.send(clientMessage);
      if (!sent) pushLog(`not connected — "${clientMessage.type}" was not sent`, 'error');
      controlError.textContent = '';
    },
    onError: (message) => {
      controlError.textContent = message;
    },
  });

  setStatus('connecting');
  socket.connect();

  window.addEventListener('beforeunload', () => socket.close());
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', main);
} else {
  main();
}
