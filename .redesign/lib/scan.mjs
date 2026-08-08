/**
 * The negative checks: things that must no longer appear anywhere.
 *
 * Absence is far cheaper to prove than presence, so every requirement that can be phrased
 * as "this must not exist any more" is enforced here rather than by inspection.
 */

import fs from 'node:fs';
import path from 'node:path';

import { blankComments } from './comments.mjs';

const SKIP_DIRS = new Set(['node_modules', '.git', 'dist', 'build', '.next', 'coverage', '.redesign']);
const STYLE_EXT = new Set(['.css', '.scss', '.sass', '.less', '.ts', '.tsx', '.js', '.jsx', '.vue', '.svelte', '.astro']);

/**
 * Every source file under `root`.
 *
 * Symlinked and junctioned directories are followed. A monorepo that links packages into
 * place is ordinary, and skipping them left whole packages unscanned while the gate went on
 * to report the redesign complete — an unscanned file and a clean file look identical in the
 * output. Tracking realpaths keeps a link pointing at an ancestor from looping forever.
 */
export const sourceFiles = (root, exts = STYLE_EXT) => {
  const out = [];
  const seen = new Set();

  const walk = (dir) => {
    let real;
    try { real = fs.realpathSync(dir); } catch { return; }
    if (seen.has(real)) return;
    seen.add(real);

    let entries;
    try { entries = fs.readdirSync(dir, { withFileTypes: true }); } catch { return; }

    for (const e of entries) {
      const full = path.join(dir, e.name);
      let isDir = e.isDirectory();
      let isFile = e.isFile();

      if (e.isSymbolicLink()) {
        try {
          const st = fs.statSync(full);           // follows the link
          isDir = st.isDirectory();
          isFile = st.isFile();
        } catch { continue; }                      // dangling
      }

      if (isDir) {
        if (!SKIP_DIRS.has(e.name)) walk(full);
      } else if (isFile && exts.has(path.extname(e.name))) {
        out.push(full);
      }
    }
  };

  walk(root);
  return out;
};

/**
 * An id selector made only of hex characters — `#abc {`, `#cafe {`, `#deed .x {` — is
 * indistinguishable from a colour by shape alone. Position tells them apart: a selector
 * runs to an opening brace with no `;` `}` or paren in between; a colour never does.
 */
const IN_SELECTOR_POSITION = /^[^{};()]*\{/;

/**
 * The basic named colours.
 *
 * Deliberately the short list rather than all 148: this check has to stay satisfiable, and
 * `linen`, `plum` and `tomato` are words before they are colours.
 *
 * Two conditions keep the false positives out, and both are needed. The word must stand
 * alone, so `whitespace` and the `-white` of a utility class are not colours. And a `:` or
 * `=` must appear earlier on the same line, so it is a value rather than prose — that is
 * what separates `border: 1px solid black` from `<p>The white background</p>`, which no
 * amount of adjacency checking can do.
 */
const NAMED = 'white|black|red|green|blue|yellow|orange|purple|gray|grey|silver|maroon|olive|lime|aqua|teal|navy|fuchsia';
const IN_VALUE = '(?<=[:=][^;{}\\n]*)';

/**
 * Raw colours outside the token file — requirement: DESIGN.md is the only visual truth.
 *
 * Covers the modern colour functions too. A check that only knew `#hex` and `rgb()` was
 * cleared by writing `oklch()` or `white`, which is not a loophole anyone had to look for —
 * it is what a current stylesheet looks like.
 */
/**
 * Hex-shaped strings that are not colours, and must never be "fixed" into tokens.
 *
 * `#dad`, `#beef`, `#added`, `#face`, `#decade` are all valid hex and all common identifiers.
 * Three shapes carry them, and each was a live false positive:
 *
 *   document.querySelector('#dad')     an id selector inside a string
 *   <a href="#added">                  a fragment link
 *   <mask><rect fill="#fff"/>          maths: #fff means SHOW, #000 means HIDE
 *
 * The mask case is the dangerous one. Recolouring a mask, clipPath or filter child to a
 * brand hue does not restyle anything — it silently changes which pixels survive.
 */
const NOT_A_COLOUR = [
  /(?:querySelector(?:All)?|getElementById|\$\(|closest|matches)\s*\(\s*['"`][^'"`]*$/,
  /\bhref\s*=\s*['"`]$/,
  /\bid\s*=\s*['"`]$/,
];

/** Inside <mask>, <clipPath> or <filter>, black and white are arithmetic, not colour. */
const MASK_CONTEXT = /<(mask|clipPath|filter)\b[^>]*>(?:(?!<\/\1>)[\s\S])*$/i;

export const RAW_COLOUR = {
  id: 'raw-colour',
  why: 'colour must come from a token, or DESIGN.md stops being the source of truth',
  pattern: new RegExp(
    '(?<![\\w-])#[0-9a-fA-F]{3,8}(?![\\w-])'
    + '|(?<![\\w-])(?:rgba?|hsla?|hwb|lab|lch|oklab|oklch|color-mix)\\s*\\('
    + `|${IN_VALUE}(?<![\\w-])(?:${NAMED})(?![\\w-])`,
    'g'
  ),
  accept: (m) => {
    const before = m.input.slice(0, m.index);
    if (m[0].startsWith('#')) {
      if (IN_SELECTOR_POSITION.test(m.input.slice(m.index + m[0].length))) return true;
      if (NOT_A_COLOUR.some((re) => re.test(before))) return true;
    }
    return MASK_CONTEXT.test(before);
  },
};

/**
 * A palette or basemap that arrives from a library, with no colour written down anywhere.
 *
 * This is the hole the raw-colour rule cannot see. Measured against fourteen real chart and
 * map snippets, `raw-colour` already flags nine — every literal hex, `rgb()`, and named
 * colour in a chart config, JSX prop or SVG fill, because they all sit in value position.
 * What it misses are the ones that name a palette instead of a colour:
 *
 *     d3.scaleOrdinal(d3.schemeCategory10)          // ten colours, none of them written
 *     colors={{ scheme: 'nivo' }}
 *     style: 'mapbox://styles/mapbox/light-v11'     // a light basemap under a dark redesign
 *     L.tileLayer('https://{s}.tile.osm.org/...')   // raster tiles nothing can restyle
 *
 * A colour scanner has nothing to find in any of them, so the chart keeps its old palette
 * and the map keeps its old basemap through an otherwise complete redesign — and those are
 * usually the most colour-saturated things on the page. A light basemap under a dark theme
 * is the single most visible way a redesign reads as half-finished.
 *
 * The fix is never to ban these: it is to pass the palette the tokens declare. Each hit
 * names something to repoint, which is why `why` reads as an instruction.
 */
const D3_SCHEMES = 'schemeCategory10|schemeAccent|schemeDark2|schemePaired|schemePastel[12]'
  + '|schemeSet[123]|schemeTableau10|schemeObservable10';
const D3_RAMPS = 'interpolate(?:Viridis|Inferno|Magma|Plasma|Turbo|Cividis|Warm|Cool|Rainbow|Sinebow|Spectral|RdYlBu|RdBu|BrBG|PiYG)';
const NAMED_SCHEMES = 'nivo|category10|accent|dark2|paired|pastel[12]|set[123]|spectral|brown_blueGreen|purpleRed_green';
/** Library themes that carry a whole palette behind one identifier. */
const NAMED_THEMES = 'VictoryTheme\\.\\w+|echarts\\.init\\s*\\([^)]*,\\s*[\'"`](?:dark|vintage|macarons|infographic|shine|roma|essos|walden)[\'"`]';
/**
 * Only the vendor's OWN default styles.
 *
 * `mapbox://styles/mapbox/light-v11` is Mapbox choosing your colours. `mapbox://styles/
 * acme-design/clx9dark2025` is a bespoke style somebody built for this product — which is
 * exactly what visual-assets.md tells you to switch to, so banning it banned the remedy.
 * The account slug is what separates them.
 */
const BASEMAPS = 'mapbox://styles/mapbox/[\\w-]+'
  + '|(?:tile|tiles|basemaps?)\\.(?:openstreetmap|osm|stamen|cartocdn|thunderforest|maptiler)[\\w.]*'
  + '|\\{s\\}\\.tile\\.[\\w.-]+';

export const LIBRARY_PALETTE = {
  id: 'library-palette',
  why: 'a palette or basemap named from a library keeps its own colours — pass the tokens instead',
  pattern: new RegExp(
    `(?<![\\w-])d3\\.(?:${D3_SCHEMES}|${D3_RAMPS})(?![\\w-])`
    + `|(?<![\\w-])(?:${D3_SCHEMES}|${D3_RAMPS})(?![\\w-])`
    + `|scheme\\s*[:=]\\s*['"\`](?:${NAMED_SCHEMES})['"\`]`
    + `|(?<![\\w-])(?:${NAMED_THEMES})`
    + `|${BASEMAPS}`,
    'g'
  ),
};

/** Physical direction properties — every one is an RTL defect waiting to happen. */
export const PHYSICAL_DIRECTION = {
  id: 'physical-direction',
  why: 'breaks when the language direction flips; use logical properties',
  pattern:
    /\b(?:margin|padding|border)-(?:left|right)\b|\btext-align\s*:\s*(?:left|right)\b|\bfloat\s*:\s*(?:left|right)\b|(?<![\w-])(?:ml|mr|pl|pr)-\d|(?<![\w-])text-(?:left|right)(?![\w-])/g,
};

/** Font sizes that are not on the scale. `scale` is the set of allowed literals. */
export const offScaleSize = (scale) => ({
  id: 'off-scale-size',
  why: 'a type scale with exceptions is not a scale',
  pattern: /\bfont-size\s*:\s*([^;}\n]+)/g,
  accept: (m) => scale.some((s) => m[1].trim().startsWith(s)) || m[1].includes('var('),
});

const lineOf = (text, index) => text.slice(0, index).split('\n').length;

/** Compare paths by forward slashes, so a Windows checkout ignores the same files. */
const posix = (p) => p.split(path.sep).join('/');

/** @returns {{file,line,rule,text}[]} */
export const scan = (files, rules, { ignore = [] } = {}) => {
  const hits = [];
  const skip = ignore.filter(Boolean).map(posix);
  for (const file of files) {
    if (skip.some((i) => posix(file).includes(i))) continue;

    let text;
    try { text = fs.readFileSync(file, 'utf8'); } catch { continue; }

    // Blanked, not removed: offsets and newlines survive, so a reported line number still
    // points at the line the violation is on.
    const code = blankComments(text, path.extname(file));

    for (const rule of rules) {
      for (const m of code.matchAll(rule.pattern)) {
        if (rule.accept?.(m)) continue;
        hits.push({ file, line: lineOf(code, m.index), rule: rule.id, text: m[0].trim().slice(0, 60) });
      }
    }
  }
  return hits;
};

/** A filename is data, not a pattern — it may legitimately contain regex metacharacters. */
const escapeRe = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

/**
 * Anything still importing a quarantined rival theme.
 *
 * Two things this must not do. It must not crash: a theme file called `theme(1).ts` built an
 * unterminated group and took the gate down with a SyntaxError. And it must not match a bare
 * substring: `palette` matched `../ui/palette-helpers`, so a file that had never heard of the
 * theme was reported as importing it, with no way for the run to reach green.
 */
export const quarantineImporters = (files, quarantined) => {
  const hits = [];
  const qPosix = quarantined.map(posix);
  const names = quarantined.map((q) => escapeRe(path.basename(q, path.extname(q))));

  for (const file of files) {
    // Compare in one separator. On Windows the raw endsWith never matched, so a quarantined
    // file was scanned against itself and reported as importing itself — an unfixable failure.
    if (qPosix.some((q) => posix(file).endsWith(q))) continue;

    let text;
    try { text = fs.readFileSync(file, 'utf8'); } catch { continue; }

    for (const [i, name] of names.entries()) {
      // The specifier has to *end* at the quarantined module: an optional path prefix that
      // finishes with `/`, then the name, then at most an extension, then the closing quote.
      // The quote itself counts as a boundary, so a bare `import 'palette'` still matches.
      const re = new RegExp(
        `(?:from|import|require|@use|@import)\\s*\\(?['"\`](?:[^'"\`]*/)?${name}(?:\\.\\w+)?['"\`]`
      );
      if (re.test(text)) hits.push({ file, rule: 'quarantine', text: quarantined[i] });
    }
  }
  return hits;
};
