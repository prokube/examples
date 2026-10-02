import { boardToRows } from '../game/board';
import { enumerateReachablePlacements } from '../game/animation';
import {
  InvalidPlacementError,
  applyPlacement,
} from '../game/engine';
import type { GameState, PieceType, PlacementMetrics } from '../game/types';

export interface CandidateDescription {
  readonly action: 'place' | 'hold_then_place';
  readonly piece: PieceType;
  readonly rotation: number;
  readonly column: number;
  readonly landingRow: number;
  readonly outcome: PlacementMetrics;
}

export interface ClefTetrisState {
  readonly board: readonly string[];
  readonly activePiece: PieceType;
  readonly nextPiece: PieceType;
  readonly heldPiece: PieceType | null;
  readonly canHold: boolean;
  readonly score: number;
  readonly lines: number;
  readonly level: number;
  readonly piecesPlaced: number;
}

export interface SystemOneRequest {
  readonly model: string;
  readonly state: ClefTetrisState;
  readonly questions: {
    readonly move: {
      readonly type: 'choice';
      readonly instructions: string;
      readonly criteria: Readonly<Record<string, CandidateDescription>>;
    };
  };
}

export class InvalidDecisionError extends Error {}

export function createDecisionRequest(state: GameState, model: string): SystemOneRequest {
  const placements = enumerateReachablePlacements(state);
  if (placements.length === 0) {
    throw new InvalidDecisionError('Game state has no legal placements');
  }

  const candidates = Object.fromEntries(
    placements.map((placement) => [
      placement.id,
      {
        action: placement.usedHold ? 'hold_then_place' : 'place',
        piece: placement.piece,
        rotation: placement.rotation,
        column: placement.x,
        landingRow: placement.y,
        outcome: placement.metrics,
      } satisfies CandidateDescription,
    ]),
  );
  const nextPiece = state.queue[0];
  if (nextPiece === undefined) throw new InvalidDecisionError('Piece queue is empty');

  return {
    model,
    state: {
      board: boardToRows(state.board),
      activePiece: state.active,
      nextPiece,
      heldPiece: state.hold,
      canHold: state.canHold,
      score: state.stats.score,
      lines: state.stats.lines,
      level: state.stats.level,
      piecesPlaced: state.stats.pieces,
    },
    questions: {
      move: {
        type: 'choice',
        instructions:
          'Choose the legal placement that best keeps the board low, avoids holes, and clears lines.',
        criteria: candidates,
      },
    },
  };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

export function decisionChoice(response: unknown): string {
  if (!isRecord(response) || !isRecord(response.answers)) {
    throw new InvalidDecisionError('CLEF response has no answers');
  }
  const move = response.answers.move;
  if (!isRecord(move) || move.type !== 'choice' || typeof move.choice !== 'string') {
    throw new InvalidDecisionError('CLEF response has no move choice');
  }
  return move.choice;
}

export function applyDecision(state: GameState, response: unknown): GameState {
  const choice = decisionChoice(response);
  try {
    return applyPlacement(state, choice);
  } catch (error) {
    if (error instanceof InvalidPlacementError) {
      throw new InvalidDecisionError('CLEF returned an unknown or stale move');
    }
    throw error;
  }
}
