import { orientation } from './tetrominoes';
import {
  BOARD_HEIGHT,
  BOARD_WIDTH,
  PIECES,
  type Board,
  type BoardMetrics,
  type Cell,
  type Coordinate,
  type PieceType,
} from './types';

export function createBoard(): Board {
  return Array.from({ length: BOARD_HEIGHT }, () =>
    Array<Cell>(BOARD_WIDTH).fill(null),
  );
}

export function boardFromRows(rows: readonly string[]): Board {
  if (rows.length !== BOARD_HEIGHT || rows.some((row) => row.length !== BOARD_WIDTH)) {
    throw new RangeError(`Board must be ${BOARD_WIDTH}x${BOARD_HEIGHT}`);
  }

  return rows.map((row) =>
    [...row].map((cell) => {
      if (cell === '.') return null;
      if (PIECES.includes(cell as PieceType)) return cell as PieceType;
      throw new TypeError(`Invalid board cell: ${cell}`);
    }),
  );
}

export function boardToRows(board: Board): readonly string[] {
  return board.map((row) => row.map((cell) => cell ?? '.').join(''));
}

export function placementCells(
  piece: PieceType,
  rotation: number,
  x: number,
  y: number,
): readonly Coordinate[] {
  return orientation(piece, rotation).map((cell) => ({
    x: x + cell.x,
    y: y + cell.y,
  }));
}

export function canPlace(
  board: Board,
  piece: PieceType,
  rotation: number,
  x: number,
  y: number,
): boolean {
  return placementCells(piece, rotation, x, y).every(
    (cell) =>
      cell.x >= 0 &&
      cell.x < BOARD_WIDTH &&
      cell.y >= 0 &&
      cell.y < BOARD_HEIGHT &&
      board[cell.y]?.[cell.x] === null,
  );
}

export function landingRow(
  board: Board,
  piece: PieceType,
  rotation: number,
  x: number,
): number | null {
  if (!canPlace(board, piece, rotation, x, 0)) return null;

  let y = 0;
  while (canPlace(board, piece, rotation, x, y + 1)) y += 1;
  return y;
}

export function spawnColumn(piece: PieceType): number {
  const cells = orientation(piece, 0);
  const width = Math.max(...cells.map(({ x }) => x)) + 1;
  return Math.floor((BOARD_WIDTH - width) / 2);
}

export function canSpawn(board: Board, piece: PieceType): boolean {
  return canPlace(board, piece, 0, spawnColumn(piece), 0);
}

export function lockPlacement(
  board: Board,
  piece: PieceType,
  rotation: number,
  x: number,
  y: number,
): { readonly board: Board; readonly clearedLines: number } {
  if (!canPlace(board, piece, rotation, x, y)) {
    throw new RangeError('Cannot lock an illegal placement');
  }

  const placed = board.map((row) => [...row]);
  for (const cell of placementCells(piece, rotation, x, y)) {
    const row = placed[cell.y];
    if (row === undefined) throw new RangeError('Placement escaped the board');
    row[cell.x] = piece;
  }

  const remaining = placed.filter((row) => row.some((cell) => cell === null));
  const clearedLines = BOARD_HEIGHT - remaining.length;
  const empty = Array.from({ length: clearedLines }, () =>
    Array<Cell>(BOARD_WIDTH).fill(null),
  );
  return { board: [...empty, ...remaining], clearedLines };
}

export function measureBoard(board: Board): BoardMetrics {
  const heights: number[] = [];
  let holes = 0;

  for (let x = 0; x < BOARD_WIDTH; x += 1) {
    const firstBlock = board.findIndex((row) => row[x] !== null);
    const height = firstBlock === -1 ? 0 : BOARD_HEIGHT - firstBlock;
    heights.push(height);
    if (firstBlock === -1) continue;

    for (let y = firstBlock + 1; y < BOARD_HEIGHT; y += 1) {
      if (board[y]?.[x] === null) holes += 1;
    }
  }

  const aggregateHeight = heights.reduce((total, height) => total + height, 0);
  const maximumHeight = Math.max(...heights);
  const bumpiness = heights.slice(1).reduce((total, height, index) => {
    const previous = heights[index];
    return total + Math.abs(height - (previous ?? 0));
  }, 0);

  return { holes, aggregateHeight, maximumHeight, bumpiness };
}
