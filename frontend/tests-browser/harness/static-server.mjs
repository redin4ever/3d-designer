// A static file server for the browser suite, on an ephemeral port.
//
// Chrome refuses `type="module"` imports from a `file://` origin (frontend/README.md
// already records this), so the smoke suite cannot open index.html off disk — it has to
// be served. This is deliberately the dumbest possible server: no caching, no directory
// listing, correct MIME types, and a record of every request it answered so a test can
// assert that nothing 404'd. A stylesheet or module that silently fails to load is
// exactly the class of defect a browser reveals and node:test cannot.

import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import { join, extname, normalize, resolve, sep } from 'node:path';

const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.mjs': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.ico': 'image/x-icon',
};

/**
 * @param {string} rootDir directory to serve (frontend/)
 * @returns {Promise<{origin: string, requests: {path: string, status: number}[], close: () => Promise<void>}>}
 */
export async function startStaticServer(rootDir) {
  const root = resolve(rootDir);
  /** @type {{path: string, status: number}[]} */
  const requests = [];
  const open = new Set();

  const server = createServer(async (req, res) => {
    const urlPath = decodeURIComponent(new URL(req.url, 'http://localhost').pathname);
    if (urlPath === '/api/textures') {
      requests.push({ path: urlPath, status: 200 });
      res.statusCode = 200;
      res.setHeader('content-type', 'application/json; charset=utf-8');
      res.end('{"materials":[]}');
      return;
    }
    if (urlPath === '/api/clients') {
      requests.push({ path: urlPath, status: 200 });
      res.statusCode = 200;
      res.setHeader('content-type', 'application/json; charset=utf-8');
      res.end('{"clients":[]}');
      return;
    }
    const relative = normalize(urlPath).replace(/^([/\\])+/, '');
    const target = resolve(join(root, relative === '' ? 'index.html' : relative));

    const record = (status) => {
      requests.push({ path: urlPath, status });
      res.statusCode = status;
    };

    // Never serve outside the served root, even if a test asks for it by mistake.
    if (target !== root && !target.startsWith(root + sep)) {
      record(403);
      res.end('forbidden');
      return;
    }

    try {
      const body = await readFile(target);
      record(200);
      res.setHeader('content-type', MIME[extname(target).toLowerCase()] ?? 'application/octet-stream');
      res.setHeader('cache-control', 'no-store');
      res.end(body);
    } catch {
      record(404);
      res.setHeader('content-type', 'text/plain; charset=utf-8');
      res.end('not found');
    }
  });

  server.on('connection', (socket) => {
    open.add(socket);
    socket.on('close', () => open.delete(socket));
  });

  await new Promise((done) => server.listen(0, '127.0.0.1', done));
  const { port } = server.address();

  return {
    origin: `http://127.0.0.1:${port}`,
    requests,
    async close() {
      for (const socket of open) socket.destroy();
      await new Promise((done) => server.close(done));
    },
  };
}
