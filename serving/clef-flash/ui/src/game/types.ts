export const BOARD_WIDTH = 10;
export const BOARD_HEIGHT = 20;

export const PIECES = ['I', 'J', 'L', 'O', 'S', 'T', 'Z'] as const;

export type PieceType = (typeof PIECES)[number];
export type Cell = PieceType | null;
export type Board = readonly (readonly Cell[])[];

export interface Coordinate {
  readonly x: number;
  readonly y: number;
}

export interface GameStats {
  readonly score: number;
  readonly lines: number;
  readonly level: number;
  readonly pieces: number;
}

export interface GameState {
  readonly board: Board;
  readonly active: PieceType;
  readonly queue: readonly PieceType[];
  readonly hold: PieceType | null;
  readonly canHold: boolean;
  readonly stats: GameStats;
  readonly seed: number;
  readonly randomState: number;
  readonly bag: readonly PieceType[];
  readonly gameOver: boolean;
}

export interface BoardMetrics {
  readonly holes: number;
  readonly aggregateHeight: number;
  readonly maximumHeight: number;
  readonly bumpiness: number;
}

export interface PlacementMetrics extends BoardMetrics {
  readonly clearedLines: number;
}

export interface Placement {
  readonly id: string;
  readonly piece: PieceType;
  readonly rotation: number;
  readonly x: number;
  readonly y: number;
  readonly usedHold: boolean;
  readonly resultingBoard: Board;
  readonly metrics: PlacementMetrics;
}
