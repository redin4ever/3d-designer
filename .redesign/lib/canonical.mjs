/**
 * One vocabulary for two sources that never agreed.
 *
 * Token files are written the way people write CSS: `#3366ff`, `hsl(220 90% 56%)`,
 * `0.5rem`. Fingerprints are captured with `getComputedStyle`, which always serialises
 * colour as `rgb()`/`rgba()` and length as `px`, whatever the stylesheet said.
 *
 * Compared as strings those sets cannot intersect, so a page built entirely from the token
 * file scored zero coverage and the gate could never pass. Both sides are normalised here
 * before anything is compared.
 */

const clamp = (n, lo, hi) => Math.min(hi, Math.max(lo, n));
const round = (n) => Math.round(n * 1000) / 1000;

/** Computed values that no token file would ever declare, so they must not count against it. */
const UNDECLARABLE = new Set([
  'normal', 'auto', 'none', 'initial', 'inherit', 'unset', 'currentcolor',
  'transparent', 'rgba(0, 0, 0, 0)', '0px', '0', 'medium', 'thin', 'thick',
]);

export const isUndeclarable = (v) => UNDECLARABLE.has(String(v).trim().toLowerCase());

const rgb = (r, g, b, a = 1) => {
  const [R, G, B] = [r, g, b].map((n) => clamp(Math.round(n), 0, 255));
  return a >= 1 ? `rgb(${R}, ${G}, ${B})` : `rgba(${R}, ${G}, ${B}, ${round(clamp(a, 0, 1))})`;
};

/**
 * The modern colour functions, converted to the same sRGB space everything else lands in.
 *
 * A browser reports every computed colour as `rgb()`, whatever you wrote. So a token file
 * written in `oklch()` — which is what Tailwind v4 and most current systems emit — matched
 * none of the rendered values and scored 0% token coverage: a gate that could never pass,
 * for doing the modern thing.
 */
const gamma = (c) => (c <= 0.0031308 ? 12.92 * c : 1.055 * c ** (1 / 2.4) - 0.055);

const oklabToRgb = (L, A, B, a) => {
  const l = (L + 0.3963377774 * A + 0.2158037573 * B) ** 3;
  const m = (L - 0.1055613458 * A - 0.0638541728 * B) ** 3;
  const s = (L - 0.0894841775 * A - 1.2914855480 * B) ** 3;
  return rgb(
    gamma(4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s) * 255,
    gamma(-1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s) * 255,
    gamma(-0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s) * 255,
    a
  );
};

/** hwb(h w b) — hue at full saturation, then whitened and blackened. */
const hwbToRgb = (h, w, b, a) => {
  const W = w / 100;
  const B = b / 100;
  if (W + B >= 1) {
    const grey = (W / (W + B)) * 255;
    return rgb(grey, grey, grey, a);
  }
  const base = hslToRgb(h, 100, 50, 1);
  const [r, g, bl] = (base.match(NUMS) ?? []).map(Number);
  const mix = (c) => c * (1 - W - B) + W * 255;
  return rgb(mix(r), mix(g), mix(bl), a);
};

const hslToRgb = (h, s, l, a) => {
  const H = ((h % 360) + 360) % 360, S = clamp(s, 0, 100) / 100, L = clamp(l, 0, 100) / 100;
  const c = (1 - Math.abs(2 * L - 1)) * S;
  const x = c * (1 - Math.abs(((H / 60) % 2) - 1));
  const m = L - c / 2;
  const [r, g, b] = H < 60 ? [c, x, 0] : H < 120 ? [x, c, 0] : H < 180 ? [0, c, x]
    : H < 240 ? [0, x, c] : H < 300 ? [x, 0, c] : [c, 0, x];
  return rgb((r + m) * 255, (g + m) * 255, (b + m) * 255, a);
};

const hex = (raw) => {
  let h = raw.slice(1);
  if (h.length === 3 || h.length === 4) h = [...h].map((c) => c + c).join('');
  if (h.length !== 6 && h.length !== 8) return null;
  const n = (i) => parseInt(h.slice(i, i + 2), 16);
  return rgb(n(0), n(2), n(4), h.length === 8 ? n(6) / 255 : 1);
};

const NUMS = /-?\d*\.?\d+(?:e-?\d+)?/g;

/**
 * @param {string} value a declared or computed CSS value
 * @param {{rootPx?:number}} opts px per rem — captured from the page where possible
 * @returns {string|null} the canonical form, or null if this is not a value worth comparing
 */
export const canonical = (value, { rootPx = 16 } = {}) => {
  const v = String(value ?? '').trim().toLowerCase();
  if (!v || isUndeclarable(v)) return null;

  if (v.startsWith('#')) return hex(v);

  const fn = /^(rgba?|hsla?)\s*\(([^)]*)\)$/.exec(v);
  if (fn) {
    const parts = (fn[2].match(NUMS) ?? []).map(Number);
    const hasAlpha = /\//.test(fn[2]) || parts.length > 3;
    const a = hasAlpha ? parts[3] ?? 1 : 1;
    if (parts.length < 3) return null;
    return fn[1].startsWith('hsl')
      ? hslToRgb(parts[0], parts[1], parts[2], a)
      : rgb(parts[0], parts[1], parts[2], a);
  }

  const modern = /^(oklch|oklab|hwb)\s*\(([^)]*)\)$/.exec(v);
  if (modern) {
    const parts = (modern[2].match(NUMS) ?? []).map(Number);
    if (parts.length < 3) return null;
    const a = /\//.test(modern[2]) ? parts[3] ?? 1 : 1;
    // Percentages are written as bare numbers by NUMS, so lightness arrives as 70 not 0.7.
    const pct = (n) => (modern[2].includes('%') && n > 1 ? n / 100 : n);
    if (modern[1] === 'hwb') return hwbToRgb(parts[0], parts[1], parts[2], a);
    const [L, C, H] = parts;
    return modern[1] === 'oklch'
      ? oklabToRgb(pct(L), C * Math.cos((H * Math.PI) / 180), C * Math.sin((H * Math.PI) / 180), a)
      : oklabToRgb(pct(L), parts[1], parts[2], a);
  }

  const len = /^(-?\d*\.?\d+)(px|rem|em)$/.exec(v);
  if (len) {
    const n = Number(len[1]);
    const px = len[2] === 'px' ? n : n * rootPx;      // em is resolved against root, an approximation
    return `${round(px)}px`;
  }

  return v;    // font families, keywords — compared as written
};

/** Canonicalise a collection, dropping anything not worth comparing. */
export const canonicalSet = (values, opts) => {
  const out = new Set();
  for (const v of values ?? []) {
    const c = canonical(v, opts);
    if (c) out.add(c);
  }
  return out;
};
