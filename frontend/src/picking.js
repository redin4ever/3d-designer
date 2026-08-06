// Which object is under that pixel.
//
// Nothing here is implemented yet (Rule 4 — tests come first).

export const NOTHING = 0;

export function createIdIndex() {
  throw new Error('picking.createIdIndex: not implemented');
}

export function pickAt(_frame, _x, _y) {
  throw new Error('picking.pickAt: not implemented');
}

export function pickInPath(_frame, _path, _options) {
  throw new Error('picking.pickInPath: not implemented');
}

export function pointInPolygon(_path, _x, _y) {
  throw new Error('picking.pointInPolygon: not implemented');
}

export function cssToFrame(_frame, _rect, _clientX, _clientY) {
  throw new Error('picking.cssToFrame: not implemented');
}
