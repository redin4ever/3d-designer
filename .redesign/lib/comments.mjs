/**
 * Blank out comments without moving anything.
 *
 * The previous version was two regexes, which failed in two ways that both mattered.
 *
 * A glob string ending in slash-star opens what looks like a block comment; the next glob
 * beginning with star-slash closes it. Everything between the two — real declarations, real
 * violations — was blanked before any rule saw it:
 *
 *   const include = "src/[*]";      <- reads as the start of a comment
 *   const HIDDEN  = '#ff0000';      <- so this violation is invisible
 *   const exclude = "[*]/dist";     <- and this ends it
 *
 * (bracketed above only so this very comment does not demonstrate the bug). And because the old
 * replacement collapsed each comment to spaces *including its newlines*, every line number
 * after a multi-line comment was reported short — a citation that sends you to the wrong
 * place is worse than no citation.
 *
 * So: a small state machine that knows about strings, and blanking that preserves both
 * length and newlines, leaving every later offset exactly where it was.
 */

const CSS_EXT = new Set(['.css', '.scss', '.sass', '.less']);

/**
 * @param {string} text source
 * @param {string} ext file extension, so `//` is only a comment where it is one
 * @returns {string} same length, same newlines, comments replaced by spaces
 */
export const blankComments = (text, ext = '') => {
  const out = [...text];
  const css = CSS_EXT.has(ext);
  const n = text.length;

  let i = 0;
  let state = 'code';
  let blockStart = -1;

  const blank = (from, to) => {
    for (let k = from; k < to; k += 1) if (out[k] !== '\n') out[k] = ' ';
  };

  while (i < n) {
    const c = text[i];
    const d = text[i + 1];

    if (state === 'code') {
      if (c === '/' && d === '*') { state = 'block'; blockStart = i; i += 2; continue; }
      if (c === '/' && d === '/' && !css) { state = 'line'; blank(i, i + 2); i += 2; continue; }
      if (c === "'") { state = 'sq'; i += 1; continue; }
      if (c === '"') { state = 'dq'; i += 1; continue; }
      if (c === '`' && !css) { state = 'tpl'; i += 1; continue; }
      i += 1;
      continue;
    }

    if (state === 'block') {
      if (c === '*' && d === '/') { blank(blockStart, i + 2); state = 'code'; blockStart = -1; i += 2; continue; }
      i += 1;
      continue;
    }

    if (state === 'line') {
      if (c === '\n') { state = 'code'; i += 1; continue; }
      out[i] = ' ';
      i += 1;
      continue;
    }

    // inside a string
    if (c === '\\') { i += 2; continue; }
    if ((state === 'sq' && c === "'") || (state === 'dq' && c === '"') || (state === 'tpl' && c === '`')) {
      state = 'code';
      i += 1;
      continue;
    }
    // An unterminated quote is far more likely an apostrophe in prose than a real string.
    if (state !== 'tpl' && c === '\n') { state = 'code'; i += 1; continue; }
    i += 1;
  }

  // A `/*` that never closes was not a comment — most likely a regex literal or a divide.
  // Leaving it "open" would blank the whole rest of the file, which is the original bug in
  // a new costume, so nothing is blanked at all.
  if (state === 'block') return out.slice(0, blockStart).join('') + text.slice(blockStart);

  return out.join('');
};
