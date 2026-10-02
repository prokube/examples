import { enumerateReachablePlacements } from '../game/animation';
import {
  InvalidPlacementError,
  applyPlacement,
} from '../game/engine';
import type {
  Board,
  GameState,
  PieceType,
  PlacementMetrics,
} from '../game/types';

export interface CandidateState {
  readonly id: string;
  readonly piece: PieceType;
  readonly rotation: number;
  readonly column: number;
  readonly landingRow: number;
  readonly board: readonly string[];
  readonly metrics: PlacementMetrics;
}

export interface CandidateCriterion {
  readonly action: string;
  readonly outcome: PlacementMetrics;
}

export interface ClefTetrisState {
  readonly game: string;
  readonly target: string;
  readonly coordinates: string;
  readonly board: readonly string[];
  readonly currentPiece: PieceType;
  readonly nextPieces: readonly PieceType[];
  readonly candidates: readonly CandidateState[];
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
      readonly instructions: {
        readonly question: string;
      };
      readonly criteria: Readonly<Record<string, CandidateCriterion>>;
    };
  };
}

export class InvalidDecisionError extends Error {}

function rowsForModel(board: Board): readonly string[] {
  return board.map((row) =>
    row.map((cell) => cell === null ? '.' : '#').join(''),
  );
}

export function createDecisionRequest(state: GameState, model: string): SystemOneRequest {
  const placements = enumerateReachablePlacements(state);
  if (placements.length === 0) {
    throw new InvalidDecisionError('Game state has no legal placements');
  }

  const candidates = placements.map((placement) => ({
    id: placement.id,
    piece: placement.piece,
    rotation: placement.rotation,
    column: placement.x,
    landingRow: placement.y,
    board: rowsForModel(placement.resultingBoard),
    metrics: placement.metrics,
  } satisfies CandidateState));
  const criteria = Object.fromEntries(
    placements.map((placement) => [
      placement.id,
      {
        action: 'Use this legal placement, fully described under the same ID in state.candidates.',
        outcome: placement.metrics,
      } satisfies CandidateCriterion,
    ]),
  );
  const nextPieces = state.queue.slice(0, 3);
  if (nextPieces.length < 3) throw new InvalidDecisionError('Piece queue is too short');

  return {
    model,
    state: {
      game: '10-column by 20-row Tetris. Filling all 10 cells of a row clears it. If the next piece cannot enter at the top, the game is over.',
      target: 'Survive and maximize total cleared lines.',
      coordinates: 'board[0] is the top row and board[19] is the bottom row. A dot is empty and # is occupied.',
      board: rowsForModel(state.board),
      currentPiece: state.active,
      nextPieces,
      candidates,
      score: state.stats.score,
      lines: state.stats.lines,
      level: state.stats.level,
      piecesPlaced: state.stats.pieces,
    },
    questions: {
      move: {
        type: 'choice',
        instructions: {
          question: 'Which legal placement best keeps the board low, avoids holes, and clears lines?',
        },
        criteria,
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
