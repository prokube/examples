import {
  boardToRows,
  canSpawn,
  createBoard,
  landingRow,
  lockPlacement,
  measureBoard,
} from './board';
import { shuffledBag, normalizeSeed } from './random';
import { TETROMINOES, orientation } from './tetrominoes';
import {
  BOARD_WIDTH,
  type Board,
  type GameState,
  type PieceType,
  type Placement,
} from './types';

const QUEUE_SIZE = 5;
const LINE_SCORES = [0, 100, 300, 500, 800] as const;

interface Supply {
  readonly queue: readonly PieceType[];
  readonly bag: readonly PieceType[];
  readonly randomState: number;
}

interface DrawResult extends Supply {
  readonly piece: PieceType;
}

export class InvalidPlacementError extends Error {}

function fillQueue(supply: Supply, minimum: number): Supply {
  const queue = [...supply.queue];
  let bag = [...supply.bag];
  let randomState = supply.randomState;

  while (queue.length < minimum) {
    if (bag.length === 0) {
      const shuffled = shuffledBag(randomState);
      bag = [...shuffled.bag];
      randomState = shuffled.randomState;
    }
    const piece = bag.shift();
    if (piece === undefined) throw new RangeError('Piece bag is empty');
    queue.push(piece);
  }

  return { queue, bag, randomState };
}

function drawPiece(supply: Supply): DrawResult {
  const available = fillQueue(supply, 1);
  const [piece, ...queue] = available.queue;
  if (piece === undefined) throw new RangeError('Piece queue is empty');
  const replenished = fillQueue({ ...available, queue }, QUEUE_SIZE);
  return { piece, ...replenished };
}

function fingerprint(value: string): string {
  let hash = 0xcbf29ce484222325n;
  for (let index = 0; index < value.length; index += 1) {
    hash ^= BigInt(value.charCodeAt(index));
    hash = BigInt.asUintN(64, hash * 0x100000001b3n);
  }
  return hash.toString(36);
}

function stateFingerprint(state: GameState): string {
  return fingerprint([
    ...boardToRows(state.board),
    state.active,
    state.queue.join(''),
    state.hold ?? '-',
    state.canHold ? '1' : '0',
    String(state.stats.score),
    String(state.stats.lines),
    String(state.stats.level),
    String(state.stats.pieces),
    String(state.seed),
    String(state.randomState),
    state.bag.join(''),
    state.gameOver ? '1' : '0',
  ].join('|'));
}

function piecePlacements(
  board: Board,
  piece: PieceType,
  usedHold: boolean,
  stateHash: string,
): readonly Placement[] {
  if (!canSpawn(board, piece)) return [];
  const placements: Placement[] = [];

  for (let rotation = 0; rotation < TETROMINOES[piece].length; rotation += 1) {
    const cells = orientation(piece, rotation);
    const width = Math.max(...cells.map(({ x }) => x)) + 1;
    for (let x = 0; x <= BOARD_WIDTH - width; x += 1) {
      const y = landingRow(board, piece, rotation, x);
      if (y === null) continue;
      const result = lockPlacement(board, piece, rotation, x, y);
      const metrics = {
        clearedLines: result.clearedLines,
        ...measureBoard(result.board),
      };
      const source = usedHold ? 'h' : 'a';
      const option = fingerprint(`${source}|${piece}|${rotation}|${x}|${y}`);
      placements.push({
        id: `v1-${stateHash}-${option}`,
        piece,
        rotation,
        x,
        y,
        usedHold,
        resultingBoard: result.board,
        metrics,
      });
    }
  }

  return placements;
}

export function enumeratePlacements(state: GameState): readonly Placement[] {
  if (state.gameOver || !canSpawn(state.board, state.active)) return [];
  const fingerprint = stateFingerprint(state);
  const placements = [
    ...piecePlacements(state.board, state.active, false, fingerprint),
  ];

  if (!state.canHold) return placements;
  const heldPiece = state.hold ?? state.queue[0];
  if (
    heldPiece === undefined ||
    (state.hold !== null && heldPiece === state.active)
  ) {
    return placements;
  }
  placements.push(...piecePlacements(state.board, heldPiece, true, fingerprint));
  return placements;
}

export function createGame(seed: number): GameState {
  const normalizedSeed = normalizeSeed(seed);
  const first = drawPiece({ queue: [], bag: [], randomState: normalizedSeed });
  const state: GameState = {
    board: createBoard(),
    active: first.piece,
    queue: first.queue,
    hold: null,
    canHold: true,
    stats: { score: 0, lines: 0, level: 1, pieces: 0 },
    seed,
    randomState: first.randomState,
    bag: first.bag,
    gameOver: false,
  };
  return { ...state, gameOver: enumeratePlacements(state).length === 0 };
}

export function applyPlacement(state: GameState, optionId: string): GameState {
  const placement = enumeratePlacements(state).find(({ id }) => id === optionId);
  if (placement === undefined) {
    throw new InvalidPlacementError('Unknown or stale placement choice');
  }

  let supply: Supply = {
    queue: state.queue,
    bag: state.bag,
    randomState: state.randomState,
  };
  let hold = state.hold;

  if (placement.usedHold) {
    hold = state.active;
    if (state.hold === null) {
      const heldDraw = drawPiece(supply);
      if (heldDraw.piece !== placement.piece) {
        throw new InvalidPlacementError('Hold choice does not match the next piece');
      }
      supply = heldDraw;
    } else if (state.hold !== placement.piece) {
      throw new InvalidPlacementError('Hold choice does not match the held piece');
    }
  }

  const next = drawPiece(supply);
  const totalLines = state.stats.lines + placement.metrics.clearedLines;
  const level = Math.floor(totalLines / 10) + 1;
  const lineScore = LINE_SCORES[placement.metrics.clearedLines] ?? 0;
  const nextState: GameState = {
    board: placement.resultingBoard,
    active: next.piece,
    queue: next.queue,
    hold,
    canHold: true,
    stats: {
      score: state.stats.score + lineScore * state.stats.level,
      lines: totalLines,
      level,
      pieces: state.stats.pieces + 1,
    },
    seed: state.seed,
    randomState: next.randomState,
    bag: next.bag,
    gameOver: false,
  };
  return {
    ...nextState,
    gameOver: enumeratePlacements(nextState).length === 0,
  };
}
