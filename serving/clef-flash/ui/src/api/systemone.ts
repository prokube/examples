import { boardToRows, placementCells } from '../game/board';
import { enumerateReachablePlacements } from '../game/animation';
import {
  InvalidPlacementError,
  applyPlacement,
} from '../game/engine';
import { TETROMINOES } from '../game/tetrominoes';
import {
  BOARD_HEIGHT,
  BOARD_WIDTH,
  type GameState,
  type PieceType,
  type PlacementMetrics,
} from '../game/types';

type CellCoordinate = readonly [x: number, y: number];
type PieceShapes = Readonly<Record<PieceType, readonly (readonly CellCoordinate[])[]>>;

function pieceShapes(piece: PieceType) {
  return TETROMINOES[piece].map((cells) =>
    cells.map(({ x, y }) => [x, y] as const),
  );
}

const PIECE_SHAPES: PieceShapes = {
  I: pieceShapes('I'),
  J: pieceShapes('J'),
  L: pieceShapes('L'),
  O: pieceShapes('O'),
  S: pieceShapes('S'),
  T: pieceShapes('T'),
  Z: pieceShapes('Z'),
};

export interface CandidateDescription {
  readonly piece: PieceType;
  readonly rotation: number;
  readonly column: number;
  readonly landingRow: number;
  readonly cells: readonly CellCoordinate[];
  readonly resultingBoard: readonly string[];
  readonly outcome: PlacementMetrics;
}

export interface ClefTetrisState {
  readonly game: 'Tetris';
  readonly objective: string;
  readonly boardEncoding: string;
  readonly coordinateSystem: string;
  readonly pieceShapeEncoding: string;
  readonly pieceShapes: PieceShapes;
  readonly board: readonly string[];
  readonly activePiece: PieceType;
  readonly nextPiece: PieceType;
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
        piece: placement.piece,
        rotation: placement.rotation,
        column: placement.x,
        landingRow: placement.y,
        cells: placementCells(
          placement.piece,
          placement.rotation,
          placement.x,
          placement.y,
        ).map(({ x, y }) => [x, y] as const),
        resultingBoard: boardToRows(placement.resultingBoard),
        outcome: placement.metrics,
      } satisfies CandidateDescription,
    ]),
  );
  const nextPiece = state.queue[0];
  if (nextPiece === undefined) throw new InvalidDecisionError('Piece queue is empty');

  return {
    model,
    state: {
      game: 'Tetris',
      objective: 'Survive and maximize cleared lines by keeping the board low and avoiding holes.',
      boardEncoding: `${BOARD_WIDTH} columns by ${BOARD_HEIGHT} rows, top row first; "." is empty and tetromino letters are occupied cells.`,
      coordinateSystem: 'Zero-based [x,y] coordinates with origin at the top-left; x increases right and y increases down.',
      pieceShapeEncoding: 'pieceShapes[piece][rotation] lists the four relative [x,y] cells; candidate cells are absolute board coordinates.',
      pieceShapes: PIECE_SHAPES,
      board: boardToRows(state.board),
      activePiece: state.active,
      nextPiece,
      score: state.stats.score,
      lines: state.stats.lines,
      level: state.stats.level,
      piecesPlaced: state.stats.pieces,
    },
    questions: {
      move: {
        type: 'choice',
        instructions:
          'You are playing Tetris. Choose the legal final placement that best supports the stated objective. Each candidate includes its exact cells, resulting board after line clears, and resulting board metrics.',
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
