import { describe, expect, it } from 'vitest';

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
    const request = createDecisionRequest(state);

    expect(request.model).toBe('clef-flash');
    expect(request.state.board).toHaveLength(20);
    expect(request.state.activePiece).toBe(state.active);
    expect(request.state.nextPiece).toBe(state.queue[0]);
    expect(request.state.heldPiece).toBeNull();
    expect(request.state.score).toBe(0);
    expect(request.questions.move.type).toBe('choice');
    expect(Object.keys(request.questions.move.criteria)).toHaveLength(
      placements.length,
    );
    expect(request.questions.move.criteria).toBe(request.state.candidates);
    for (const placement of placements) {
      expect(request.questions.move.criteria[placement.id]).toEqual({
        action: placement.usedHold ? 'hold_then_place' : 'place',
        piece: placement.piece,
        rotation: placement.rotation,
        column: placement.x,
        landingRow: placement.y,
        outcome: placement.metrics,
      });
    }
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
