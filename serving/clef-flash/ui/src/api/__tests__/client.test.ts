import { describe, expect, it, vi } from 'vitest';

import { applyPlacement, createGame } from '../../game';
import {
  heuristicDecision,
  requestClefDecision,
  resolveModelName,
  resolveSystemOneUrl,
} from '../client';
import { decisionPlacements } from '../systemone';

describe('runtime API client', () => {
  it('resolves the endpoint against a configured runtime base path', () => {
    const page = {
      baseURI: 'https://example.test/notebook/team/demo/',
      querySelector: vi.fn(() => ({ content: 'inference/systemone' })),
    } as unknown as Pick<Document, 'baseURI' | 'querySelector'>;

    expect(resolveSystemOneUrl(page).href).toBe(
      'https://example.test/notebook/team/demo/inference/systemone',
    );
  });

  it('requires a runtime-configured model name', () => {
    const configured = {
      querySelector: vi.fn(() => ({ content: 'deployment-model' })),
    } as unknown as Pick<Document, 'querySelector'>;
    const missing = {
      querySelector: vi.fn(() => ({ content: '  ' })),
    } as unknown as Pick<Document, 'querySelector'>;

    expect(resolveModelName(configured)).toBe('deployment-model');
    expect(() => resolveModelName(missing)).toThrow(
      'The CLEF model name is not configured.',
    );
  });

  it('ranks deterministic heuristic choices', () => {
    const first = heuristicDecision(createGame(42));
    const second = heuristicDecision(createGame(42));
    expect(first.choice).toBe(second.choice);
    expect(first.ranked).toEqual(second.ranked);
  });

  it('runs a sustained seeded game with the heuristic policy', () => {
    let state = createGame(20261001);

    for (let turn = 0; turn < 500; turn += 1) {
      expect(state.gameOver).toBe(false);
      state = applyPlacement(state, heuristicDecision(state).choice);
    }

    expect(state.stats.pieces).toBe(500);
    expect(state.stats.lines).toBeGreaterThan(0);
  });

  it('accepts and ranks a complete CLEF choice response', async () => {
    const state = createGame(4);
    const placements = decisionPlacements(state);
    const selected = placements[1];
    expect(selected).toBeDefined();
    const probabilities = Object.fromEntries(
      placements.map(({ id }, index) => [id, index === 1 ? 0.8 : 0.2 / (placements.length - 1)]),
    );
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(
      new Response(
        JSON.stringify({
          answers: {
            move: { type: 'choice', choice: selected?.id, confidence: 0.8, probabilities },
          },
        }),
        { status: 200 },
      ),
    );

    const result = await requestClefDecision(
      state,
      new AbortController().signal,
      fetcher,
      'configured-model',
    );

    expect(fetcher).toHaveBeenCalledOnce();
    expect(fetcher).toHaveBeenCalledWith(
      expect.any(URL),
      expect.objectContaining({
        body: expect.stringContaining('"model":"configured-model"'),
      }),
    );
    expect(result.choice).toBe(selected?.id);
    expect(result.ranked[0]?.placement.id).toBe(selected?.id);
  });

  it('puts the selected move first when CLEF probabilities are tied', async () => {
    const state = createGame(7);
    const placements = decisionPlacements(state);
    const selected = placements.at(-1);
    expect(selected).toBeDefined();
    const probability = 1 / placements.length;
    const probabilities = Object.fromEntries(
      placements.map(({ id }) => [id, probability]),
    );
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(
      new Response(
        JSON.stringify({
          answers: {
            move: {
              type: 'choice',
              choice: selected?.id,
              confidence: probability,
              probabilities,
            },
          },
        }),
        { status: 200 },
      ),
    );

    const result = await requestClefDecision(
      state,
      new AbortController().signal,
      fetcher,
      'configured-model',
    );

    expect(result.ranked[0]?.placement.id).toBe(selected?.id);
  });

  it('rejects incomplete probabilities with a safe message', async () => {
    const state = createGame(5);
    const choice = decisionPlacements(state)[0];
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(
      new Response(
        JSON.stringify({
          answers: {
            move: {
              type: 'choice',
              choice: choice?.id,
              confidence: 1,
              probabilities: { [choice?.id ?? 'missing']: 1 },
            },
          },
        }),
        { status: 200 },
      ),
    );

    await expect(
      requestClefDecision(
        state,
        new AbortController().signal,
        fetcher,
        'configured-model',
      ),
    ).rejects.toThrow('The model returned invalid probabilities.');
  });

  it.each([
    ['a distribution that does not sum to one', 0.8, false, false],
    ['confidence that differs from the selected probability', 1, true, false],
    ['an unknown probability option', 1, false, true],
  ])('rejects %s', async (_label, scale, mismatch, includeUnknown) => {
    const state = createGame(6);
    const placements = decisionPlacements(state);
    const choice = placements[0];
    expect(choice).toBeDefined();
    const base = 1 / placements.length;
    const probabilities = Object.fromEntries(
      placements.map(({ id }) => [id, base * scale]),
    );
    if (includeUnknown) probabilities.unknown = 0;
    const confidence = mismatch ? 0.5 : base * scale;
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(
      new Response(
        JSON.stringify({
          answers: {
            move: {
              type: 'choice',
              choice: choice?.id,
              confidence,
              probabilities,
            },
          },
        }),
        { status: 200 },
      ),
    );

    await expect(
      requestClefDecision(
        state,
        new AbortController().signal,
        fetcher,
        'configured-model',
      ),
    ).rejects.toThrow('The model returned invalid probabilities.');
  });
});
