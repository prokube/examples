import { canPlace, spawnColumn } from './board';
import { enumeratePlacements } from './engine';
import { TETROMINOES } from './tetrominoes';
import type { Board, GameState, PieceType, Placement } from './types';

export interface AnimationFrame {
  readonly piece: PieceType;
  readonly rotation: number;
  readonly x: number;
  readonly y: number;
  readonly phase: 'rotate' | 'move' | 'position' | 'drop';
}

interface SearchNode {
  readonly x: number;
  readonly y: number;
  readonly rotation: number;
  readonly parent: string | null;
  readonly phase: AnimationFrame['phase'];
}

function nodeKey(x: number, y: number, rotation: number): string {
  return `${x}:${y}:${rotation}`;
}

function search(board: Board, piece: PieceType): ReadonlyMap<string, SearchNode> {
  const start: SearchNode = {
    x: spawnColumn(piece),
    y: 0,
    rotation: 0,
    parent: null,
    phase: 'position',
  };
  if (!canPlace(board, piece, start.rotation, start.x, start.y)) return new Map();

  const startKey = nodeKey(start.x, start.y, start.rotation);
  const nodes = new Map([[startKey, start]]);
  const queue = [startKey];

  for (let index = 0; index < queue.length; index += 1) {
    const currentKey = queue[index];
    if (currentKey === undefined) continue;
    const current = nodes.get(currentKey);
    if (current === undefined) continue;
    const rotations = TETROMINOES[piece].length;
    const candidates: readonly Omit<SearchNode, 'parent'>[] = [
      { ...current, x: current.x - 1, phase: 'move' },
      { ...current, x: current.x + 1, phase: 'move' },
      { ...current, rotation: (current.rotation + 1) % rotations, phase: 'rotate' },
      { ...current, y: current.y + 1, phase: 'position' },
    ];

    for (const candidate of candidates) {
      const candidateKey = nodeKey(candidate.x, candidate.y, candidate.rotation);
      if (
        nodes.has(candidateKey) ||
        !canPlace(
          board,
          piece,
          candidate.rotation,
          candidate.x,
          candidate.y,
        )
      ) {
        continue;
      }
      nodes.set(candidateKey, { ...candidate, parent: currentKey });
      queue.push(candidateKey);
    }
  }

  return nodes;
}

function targetNode(
  nodes: ReadonlyMap<string, SearchNode>,
  placement: Placement,
): readonly [string, SearchNode] | null {
  const targets = [...nodes.entries()]
    .filter(([, node]) =>
      node.x === placement.x &&
      node.rotation === placement.rotation &&
      node.y <= placement.y,
    )
    .sort((left, right) => left[1].y - right[1].y);
  return targets[0] ?? null;
}

function route(
  nodes: ReadonlyMap<string, SearchNode>,
  target: readonly [string, SearchNode],
  piece: PieceType,
): readonly AnimationFrame[] {
  const frames: AnimationFrame[] = [];
  let key: string | null = target[0];
  while (key !== null) {
    const node = nodes.get(key);
    if (node === undefined) return [];
    frames.push({
      piece,
      rotation: node.rotation,
      x: node.x,
      y: node.y,
      phase: node.phase,
    });
    key = node.parent;
  }
  return frames.reverse();
}

export function animationFrames(
  board: Board,
  placement: Placement,
): readonly AnimationFrame[] | null {
  const nodes = search(board, placement.piece);
  const target = targetNode(nodes, placement);
  if (target === null) return null;
  const path = route(nodes, target, placement.piece);
  if (path.length === 0) return null;
  const drop = Array.from(
    { length: placement.y - target[1].y + 1 },
    (_, offset) => ({
      piece: placement.piece,
      rotation: placement.rotation,
      x: placement.x,
      y: target[1].y + offset,
      phase: 'drop' as const,
    }),
  );
  return [...path, ...drop];
}

export function enumerateReachablePlacements(
  state: GameState,
): readonly Placement[] {
  const placements = enumeratePlacements(state);
  const searches = new Map<PieceType, ReadonlyMap<string, SearchNode>>();
  return placements.filter((placement) => {
    const nodes = searches.get(placement.piece) ?? search(state.board, placement.piece);
    searches.set(placement.piece, nodes);
    return targetNode(nodes, placement) !== null;
  });
}
