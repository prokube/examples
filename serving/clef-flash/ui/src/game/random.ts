import { PIECES, type PieceType } from './types';

const ZERO_SEED = 0x6d2b79f5;

export function normalizeSeed(seed: number): number {
  if (!Number.isSafeInteger(seed)) throw new TypeError('Seed must be a safe integer');
  const normalized = seed >>> 0;
  return normalized === 0 ? ZERO_SEED : normalized;
}

function nextRandom(state: number): readonly [number, number] {
  let next = state >>> 0;
  next ^= next << 13;
  next ^= next >>> 17;
  next ^= next << 5;
  const normalized = next >>> 0;
  return [normalized / 0x1_0000_0000, normalized];
}

export function shuffledBag(randomState: number): {
  readonly bag: readonly PieceType[];
  readonly randomState: number;
} {
  const bag = [...PIECES];
  let state = randomState;

  for (let index = bag.length - 1; index > 0; index -= 1) {
    const [random, nextState] = nextRandom(state);
    state = nextState;
    const target = Math.floor(random * (index + 1));
    const value = bag[index];
    const replacement = bag[target];
    if (value === undefined || replacement === undefined) {
      throw new RangeError('Invalid bag shuffle index');
    }
    bag[index] = replacement;
    bag[target] = value;
  }

  return { bag, randomState: state };
}
