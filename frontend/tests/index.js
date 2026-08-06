// Entry-point fallback for a Node CLI quirk in this environment (Node v24.18.0 on
// Windows): `node --test <bare-directory>` in space-separated form — exactly the
// invocation `test:frontend` runs in the root package.json — fails to recurse the
// directory and instead falls back to resolving it as an ordinary script entry point
// (`Module._resolveFilename`, which looks for this directory's `index.js`). Importing
// every sibling `*.test.js` file here registers all of this module's tests with the
// `--test` harness that is already active, so `node --test frontend/tests/` reports
// real pass/fail counts and a correct exit code end to end.
//
// This file is inert if the bug is ever fixed upstream (or on a Node build where the
// directory form already works, or via `node --test=frontend/tests/`): it does not
// match any default test-file naming pattern (`*.test.js`), so Node's real recursive
// discovery never independently loads it, and there is no double-execution risk either
// way. See frontend/CLAUDE.md "Known environment quirk" for the verification steps.
// Every *.test.js here must be listed below or the directory run silently skips it —
// which is not hypothetical: camera.test.js was written, passed when run directly, and
// reported nothing at all through `npm run test:frontend` until it was added here.
import './camera.test.js';
import './controls.test.js';
import './log.test.js';
import './raster.test.js';
import './socket.test.js';
import './tokens.test.js';
import './viewport.test.js';
