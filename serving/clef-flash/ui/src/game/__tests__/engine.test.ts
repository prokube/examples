import { describe, expect, it } from 'vitest';

import { boardFromRows, boardToRows, canPlace, placementCells } from '../board';
import {
  InvalidPlacementError,
  applyPlacement,
  createGame,
  enumeratePlacements,
} from '../engine';
import { TETROMINOES } from '../tetrominoes';
import { BOARD_HEIGHT, BOARD_WIDTH, PIECES } from '../types';

function rows(...bottom: readonly string[]): readonly string[] {
  return [
    ...Array<string>(BOARD_HEIGHT - bottom.length).fill('.'.repeat(BOARD_WIDTH)),
    ...bottom,
  ];
}

describe('tetromino orientations', () => {
  it('contains the unique SRS placement orientations', () => {
    expect(
      Object.fromEntries(PIECES.map((piece) => [piece, TETROMINOES[piece].length])),
    ).toEqual({ I: 2, J: 4, L: 4, O: 1, S: 2, T: 4, Z: 2 });
  });

  it('uses the four normalized SRS T orientations in clockwise order', () => {
    expect(TETROMINOES.T).toEqual([
      [
        { x: 1, y: 0 },
        { x: 0, y: 1 },
        { x: 1, y: 1 },
        { x: 2, y: 1 },
      ],
      [
        { x: 0, y: 0 },
        { x: 0, y: 1 },
        { x: 1, y: 1 },
        { x: 0, y: 2 },
      ],
      [
        { x: 0, y: 0 },
        { x: 1, y: 0 },
        { x: 2, y: 0 },
        { x: 1, y: 1 },
      ],
      [
        { x: 1, y: 0 },
        { x: 0, y: 1 },
        { x: 1, y: 1 },
        { x: 1, y: 2 },
      ],
    ]);
  });
});

describe('placement enumeration', () => {
  it('enumerates all direct hard-drop placements on an empty board', () => {
    const state = { ...createGame(7), active: 'I' as const };
    const placements = enumeratePlacements(state);

    expect(placements).toHaveLength(17);
    expect(new Set(placements.map(({ id }) => id)).size).toBe(placements.length);
  });

  it('only returns in-bounds, collision-free, terminal placements', () => {
    const state = createGame(42);

    for (const placement of enumeratePlacements(state)) {
      expect(
        canPlace(
          state.board,
          placement.piece,
          placement.rotation,
          placement.x,
          placement.y,
        ),
      ).toBe(true);
      expect(
        canPlace(
          state.board,
          placement.piece,
          placement.rotation,
          placement.x,
          placement.y + 1,
        ),
      ).toBe(false);
      for (const cell of placementCells(
        placement.piece,
        placement.rotation,
        placement.x,
        placement.y,
      )) {
        expect(cell.x).toBeGreaterThanOrEqual(0);
        expect(cell.x).toBeLessThan(BOARD_WIDTH);
        expect(cell.y).toBeGreaterThanOrEqual(0);
        expect(cell.y).toBeLessThan(BOARD_HEIGHT);
      }
    }
  });

  it('scores line clears and advances levels without mutating the source state', () => {
    const base = createGame(15);
    const state = {
      ...base,
      board: boardFromRows(rows('IIIIIIII..', 'IIIIIIII..')),
      active: 'O' as const,
      stats: { score: 50, lines: 9, level: 1, pieces: 4 },
    };
    const before = JSON.stringify(state);
    const choice = enumeratePlacements(state).find(
      ({ x, metrics }) => x === 8 && metrics.clearedLines === 2,
    );
    expect(choice).toBeDefined();

    const next = applyPlacement(state, choice?.id ?? 'missing');

    expect(next.stats).toEqual({ score: 350, lines: 11, level: 2, pieces: 5 });
    expect(JSON.stringify(state)).toBe(before);
    expect(boardToRows(state.board).slice(-2)).toEqual([
      'IIIIIIII..',
      'IIIIIIII..',
    ]);
  });

  it('ends the game when the centered spawn position is blocked', () => {
    const state = {
      ...createGame(16),
      active: 'I' as const,
      board: boardFromRows(['...T......', ...rows().slice(1)]),
    };

    expect(enumeratePlacements(state)).toEqual([]);
  });

  it('produces identical sequences and transitions for the same seed', () => {
    let left = createGame(20261001);
    let right = createGame(20261001);

    for (let turn = 0; turn < 40 && !left.gameOver; turn += 1) {
      expect(right).toEqual(left);
      const choices = [...enumeratePlacements(left)].sort(
        (first, second) =>
          first.metrics.holes - second.metrics.holes ||
          first.metrics.aggregateHeight - second.metrics.aggregateHeight ||
          first.id.localeCompare(second.id),
      );
      const choice = choices[0];
      expect(choice).toBeDefined();
      left = applyPlacement(left, choice?.id ?? 'missing');
      right = applyPlacement(right, choice?.id ?? 'missing');
    }

    expect(right).toEqual(left);
  });

  it('rejects unknown and stale choices', () => {
    const state = createGame(99);
    const choice = enumeratePlacements(state)[0];
    expect(choice).toBeDefined();

    expect(() => applyPlacement(state, 'unknown')).toThrow(InvalidPlacementError);
    const next = applyPlacement(state, choice?.id ?? 'missing');
    expect(() => applyPlacement(next, choice?.id ?? 'missing')).toThrow(
      InvalidPlacementError,
    );
  });
});
