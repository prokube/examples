import { describe, expect, it } from 'vitest';

import { createGame, enumeratePlacements } from '../../game/engine';
import {
  InvalidDecisionError,
  applyDecision,
  createDecisionRequest,
  decisionChoice,
  decisionPlacements,
} from '../systemone';

describe('CLEF SystemOne policy contract', () => {
  it('encodes the complete state and up to 12 selected options', () => {
    const state = createGame(123);
    const legal = enumeratePlacements(state);
    const placements = decisionPlacements(state);
    const selectedIndices = placements.map(({ id }) =>
      legal.findIndex((placement) => placement.id === id),
    );
    const request = createDecisionRequest(state, 'configured-model');

    expect(request.model).toBe('configured-model');
    expect(request.state.game).toContain('10-column by 20-row Tetris');
    expect(request.state.board).toHaveLength(20);
    expect(request.state.board.every((row) => /^[.#]{10}$/.test(row))).toBe(true);
    expect(request.state.currentPiece).toBe(state.active);
    expect(request.state.nextPieces).toEqual(state.queue.slice(0, 3));
    expect(request.state.score).toBe(0);
    expect(request.state).not.toHaveProperty('heldPiece');
    expect(request.state).not.toHaveProperty('canHold');
    expect(request.questions.move.type).toBe('choice');
    expect(legal.length).toBeGreaterThan(12);
    expect(placements).toHaveLength(12);
    expect(selectedIndices).toEqual(
      [...selectedIndices].sort((left, right) => left - right),
    );
    expect(request.state.candidates).toHaveLength(placements.length);
    expect(Object.keys(request.questions.move.criteria)).toHaveLength(
      placements.length,
    );
    for (const placement of placements) {
      expect(request.state.candidates.find(({ id }) => id === placement.id)).toEqual({
        id: placement.id,
        piece: placement.piece,
        rotation: placement.rotation,
        column: placement.x,
        landingRow: placement.y,
        board: placement.resultingBoard.map((row) =>
          row.map((cell) => cell === null ? '.' : '#').join(''),
        ),
        metrics: placement.metrics,
      });
      expect(request.questions.move.criteria[placement.id]).toEqual({
        action: 'Use this legal placement, fully described under the same ID in state.candidates.',
        outcome: placement.metrics,
      });
    }
  });

  it('uses stable opaque option IDs', () => {
    const state = createGame(123);
    const first = createDecisionRequest(state, 'configured-model');
    const second = createDecisionRequest(state, 'configured-model');
    const keys = Object.keys(first.questions.move.criteria);
    const placementIds = decisionPlacements(state).map(({ id }) => id);

    expect(keys).toEqual(Object.keys(second.questions.move.criteria));
    expect(new Set(keys)).toEqual(new Set(placementIds));
    expect(first.state.candidates.map(({ id }) => id)).toEqual(placementIds);
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
