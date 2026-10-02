import { describe, expect, it } from 'vitest';

import { placementCells } from '../../game/board';
import { createGame, enumeratePlacements } from '../../game/engine';
import {
  InvalidDecisionError,
  applyDecision,
  createDecisionRequest,
  decisionChoice,
} from '../systemone';

describe('CLEF SystemOne policy contract', () => {
  it('encodes the complete state and every legal option', () => {
    const state = createGame(123);
    const placements = enumeratePlacements(state);
    const request = createDecisionRequest(state, 'configured-model');

    expect(request.model).toBe('configured-model');
    expect(request.state.game).toBe('Tetris');
    expect(request.state.boardEncoding).toContain('top row first');
    expect(request.state.coordinateSystem).toContain('top-left');
    expect(request.state.pieceShapeEncoding).toContain('relative [x,y]');
    expect(request.state.pieceShapes.I).toEqual([
      [[0, 0], [1, 0], [2, 0], [3, 0]],
      [[0, 0], [0, 1], [0, 2], [0, 3]],
    ]);
    expect(request.state.board).toHaveLength(20);
    expect(request.state.activePiece).toBe(state.active);
    expect(request.state.nextPiece).toBe(state.queue[0]);
    expect(request.state.score).toBe(0);
    expect(request.state).not.toHaveProperty('heldPiece');
    expect(request.state).not.toHaveProperty('canHold');
    expect(request.state).not.toHaveProperty('candidates');
    expect(request.questions.move.type).toBe('choice');
    expect(Object.keys(request.questions.move.criteria)).toHaveLength(
      placements.length,
    );
    for (const placement of placements) {
      expect(request.questions.move.criteria[placement.id]).toEqual({
        piece: placement.piece,
        rotation: placement.rotation,
        column: placement.x,
        landingRow: placement.y,
        cells: placementCells(
          placement.piece,
          placement.rotation,
          placement.x,
          placement.y,
        ).map(({ x, y }) => [x, y]),
        outcome: placement.metrics,
      });
    }
  });

  it('uses stable opaque option IDs', () => {
    const state = createGame(123);
    const first = createDecisionRequest(state, 'configured-model');
    const second = createDecisionRequest(state, 'configured-model');
    const keys = Object.keys(first.questions.move.criteria);
    const placementIds = enumeratePlacements(state).map(({ id }) => id);

    expect(keys).toEqual(Object.keys(second.questions.move.criteria));
    expect(new Set(keys)).toEqual(new Set(placementIds));
    expect(keys.every((id) => /^v1-[a-z0-9]+-[a-z0-9]+$/.test(id))).toBe(true);
  });

  it('applies only the choice ID and ignores untrusted extra coordinates', () => {
    const state = createGame(456);
    const choice = enumeratePlacements(state)[0];
    expect(choice).toBeDefined();

    const next = applyDecision(state, {
      answers: {
        move: {
          type: 'choice',
          choice: choice?.id,
          x: 999,
          y: 999,
        },
      },
    });

    expect(next.stats.pieces).toBe(1);
    expect(next.board).toEqual(choice?.resultingBoard);
  });

  it('rejects malformed, unknown, and stale model responses', () => {
    const state = createGame(789);
    const choice = enumeratePlacements(state)[0];
    expect(choice).toBeDefined();

    expect(() => decisionChoice({ answers: {} })).toThrow(InvalidDecisionError);
    expect(() =>
      applyDecision(state, {
        answers: { move: { type: 'choice', choice: 'unknown' } },
      }),
    ).toThrow(InvalidDecisionError);

    const next = applyDecision(state, {
      answers: { move: { type: 'choice', choice: choice?.id } },
    });
    expect(() =>
      applyDecision(next, {
        answers: { move: { type: 'choice', choice: choice?.id } },
      }),
    ).toThrow(InvalidDecisionError);
  });

  it('invalidates choices when only score context changes', () => {
    const state = createGame(790);
    const choice = enumeratePlacements(state)[0];
    expect(choice).toBeDefined();
    const changed = {
      ...state,
      stats: { ...state.stats, score: state.stats.score + 1 },
    };

    expect(() =>
      applyDecision(changed, {
        answers: { move: { type: 'choice', choice: choice?.id } },
      }),
    ).toThrow(InvalidDecisionError);
  });
});
