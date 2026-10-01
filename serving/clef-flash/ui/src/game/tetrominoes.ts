import type { Coordinate, PieceType } from './types';

type Orientation = readonly Coordinate[];

const SPAWN_CELLS: Record<PieceType, Orientation> = {
  I: [
    { x: 0, y: 0 },
    { x: 1, y: 0 },
    { x: 2, y: 0 },
    { x: 3, y: 0 },
  ],
  J: [
    { x: 0, y: 0 },
    { x: 0, y: 1 },
    { x: 1, y: 1 },
    { x: 2, y: 1 },
  ],
  L: [
    { x: 2, y: 0 },
    { x: 0, y: 1 },
    { x: 1, y: 1 },
    { x: 2, y: 1 },
  ],
  O: [
    { x: 0, y: 0 },
    { x: 1, y: 0 },
    { x: 0, y: 1 },
    { x: 1, y: 1 },
  ],
  S: [
    { x: 1, y: 0 },
    { x: 2, y: 0 },
    { x: 0, y: 1 },
    { x: 1, y: 1 },
  ],
  T: [
    { x: 1, y: 0 },
    { x: 0, y: 1 },
    { x: 1, y: 1 },
    { x: 2, y: 1 },
  ],
  Z: [
    { x: 0, y: 0 },
    { x: 1, y: 0 },
    { x: 1, y: 1 },
    { x: 2, y: 1 },
  ],
};

function normalize(cells: Orientation): Orientation {
  const minimumX = Math.min(...cells.map(({ x }) => x));
  const minimumY = Math.min(...cells.map(({ y }) => y));
  const normalized = cells
    .map(({ x, y }) => ({ x: x - minimumX, y: y - minimumY }))
    .sort((left, right) => left.y - right.y || left.x - right.x);
  return Object.freeze(normalized.map((cell) => Object.freeze(cell)));
}

function rotate(cells: Orientation): Orientation {
  const height = Math.max(...cells.map(({ y }) => y)) + 1;
  return normalize(cells.map(({ x, y }) => ({ x: height - 1 - y, y: x })));
}

function key(cells: Orientation): string {
  return cells.map(({ x, y }) => `${x},${y}`).join(';');
}

function uniqueOrientations(spawn: Orientation): readonly Orientation[] {
  const result: Orientation[] = [];
  const seen = new Set<string>();
  let current = normalize(spawn);

  for (let rotation = 0; rotation < 4; rotation += 1) {
    const orientationKey = key(current);
    if (!seen.has(orientationKey)) {
      result.push(current);
      seen.add(orientationKey);
    }
    current = rotate(current);
  }

  return Object.freeze(result);
}

export const TETROMINOES: Readonly<Record<PieceType, readonly Orientation[]>> =
  Object.freeze({
    I: uniqueOrientations(SPAWN_CELLS.I),
    J: uniqueOrientations(SPAWN_CELLS.J),
    L: uniqueOrientations(SPAWN_CELLS.L),
    O: uniqueOrientations(SPAWN_CELLS.O),
    S: uniqueOrientations(SPAWN_CELLS.S),
    T: uniqueOrientations(SPAWN_CELLS.T),
    Z: uniqueOrientations(SPAWN_CELLS.Z),
  });

export function orientation(piece: PieceType, rotation: number): Orientation {
  const cells = TETROMINOES[piece][rotation];
  if (cells === undefined) {
    throw new RangeError(`Invalid ${piece} rotation: ${rotation}`);
  }
  return cells;
}
