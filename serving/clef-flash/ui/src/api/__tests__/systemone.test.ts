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
    const request = createDecisionRequest(state, 'configured-model');

    expect(request.model).toBe('configured-model');
    expect(request.state.board).toHaveLength(20);
    expect(request.state.activePiece).toBe(state.active);
    expect(request.state.nextPiece).toBe(state.queue[0]);
    expect(request.state.heldPiece).toBeNull();
    expect(request.state.score).toBe(0);
    expect(request.state).not.toHaveProperty('candidates');
    expect(request.questions.move.type).toBe('choice');
    expect(Object.keys(request.questions.move.criteria)).toHaveLength(
      placements.length,
    );
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

  it('uses stable opaque option IDs that do not sort active moves before hold moves', () => {
    const state = createGame(123);
    const first = createDecisionRequest(state, 'configured-model');
    const second = createDecisionRequest(state, 'configured-model');
    const keys = Object.keys(first.questions.move.criteria);
    const placements = new Map(
      enumeratePlacements(state).map((placement) => [placement.id, placement]),
    );
    const sorted = [...keys].sort().map((id) => placements.get(id));
    const firstHold = sorted.findIndex((placement) => placement?.usedHold);

    expect(keys).toEqual(Object.keys(second.questions.move.criteria));
    expect(new Set(keys)).toEqual(new Set(placements.keys()));
    expect(keys.every((id) => !/-[ah]-[IOTSZJL]-r\d-x\d-y\d+$/.test(id))).toBe(true);
    expect(firstHold).toBeGreaterThanOrEqual(0);
    expect(sorted.slice(firstHold + 1).some((placement) => !placement?.usedHold)).toBe(true);
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
