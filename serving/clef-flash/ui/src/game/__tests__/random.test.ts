import { describe, expect, it } from 'vitest';

import { normalizeSeed, shuffledBag } from '../random';
import { PIECES } from '../types';

describe('seven-bag generator', () => {
  it('returns every tetromino exactly once in each seeded bag', () => {
    let randomState = normalizeSeed(20261001);
    const expected = [...PIECES].sort();

    for (let index = 0; index < 20; index += 1) {
      const result = shuffledBag(randomState);
      expect([...result.bag].sort()).toEqual(expected);
      expect(new Set(result.bag).size).toBe(PIECES.length);
      randomState = result.randomState;
    }
  });

  it('normalizes zero and rejects non-integer seeds', () => {
    expect(normalizeSeed(0)).not.toBe(0);
    expect(() => normalizeSeed(1.5)).toThrow(TypeError);
  });
});
