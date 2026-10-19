import { describe, expect, it } from 'vitest';

import {
  boardFromRows,
  boardToRows,
  canPlace,
  canSpawn,
  createBoard,
  lockPlacement,
  measureBoard,
  placementCells,
} from '../board';
import { BOARD_HEIGHT, BOARD_WIDTH } from '../types';

function rows(...bottom: readonly string[]): readonly string[] {
  return [
    ...Array<string>(BOARD_HEIGHT - bottom.length).fill('.'.repeat(BOARD_WIDTH)),
    ...bottom,
  ];
}

describe('board physics', () => {
  it('rejects collisions and every out-of-bounds direction', () => {
    const board = boardFromRows(rows('....T.....'));

    expect(canPlace(board, 'O', 0, -1, 0)).toBe(false);
    expect(canPlace(board, 'O', 0, BOARD_WIDTH - 1, 0)).toBe(false);
    expect(canPlace(board, 'O', 0, 0, -1)).toBe(false);
    expect(canPlace(board, 'O', 0, 0, BOARD_HEIGHT - 1)).toBe(false);
    expect(canPlace(board, 'I', 0, 2, BOARD_HEIGHT - 1)).toBe(false);
    expect(canPlace(board, 'I', 0, 4, BOARD_HEIGHT - 1)).toBe(false);
    expect(canPlace(createBoard(), 'I', 0, 3, BOARD_HEIGHT - 1)).toBe(true);
  });

  it('clears complete rows and shifts remaining cells down', () => {
    const board = boardFromRows(rows('..........', 'IIIIIIII..'));
    const result = lockPlacement(board, 'O', 0, 8, BOARD_HEIGHT - 2);

    expect(result.clearedLines).toBe(1);
    expect(boardToRows(result.board).at(-1)).toBe('........OO');
  });

  it('clears multiple rows in one placement', () => {
    const board = boardFromRows(rows('IIIIIIII..', 'IIIIIIII..'));
    const result = lockPlacement(board, 'O', 0, 8, BOARD_HEIGHT - 2);

    expect(result.clearedLines).toBe(2);
    expect(boardToRows(result.board).slice(-2)).toEqual([
      '..........',
      '..........',
    ]);
  });

  it('measures holes, heights, and bumpiness', () => {
    const board = boardFromRows(rows('I.........', '..........', 'I.I.......'));

    expect(measureBoard(board)).toEqual({
      holes: 1,
      aggregateHeight: 4,
      maximumHeight: 3,
      bumpiness: 5,
    });
  });

  it('returns the four translated cells for a placement', () => {
    const cells = placementCells('T', 0, 3, 4);

    expect(cells).toHaveLength(4);
    expect(new Set(cells.map(({ x, y }) => `${x},${y}`)).size).toBe(4);
  });

  it('requires a clear centered spawn position', () => {
    const blocked = boardFromRows([
      '...T......',
      ...rows().slice(1),
    ]);

    expect(canSpawn(createBoard(), 'I')).toBe(true);
    expect(canSpawn(blocked, 'I')).toBe(false);
  });
});
