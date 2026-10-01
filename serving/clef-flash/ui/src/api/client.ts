import { createDecisionRequest } from './systemone';
import { enumeratePlacements } from '../game/engine';
import type { GameState, Placement } from '../game/types';

export interface RankedChoice {
  readonly placement: Placement;
  readonly probability: number;
}

export interface PolicyDecision {
  readonly choice: string;
  readonly confidence: number;
  readonly ranked: readonly RankedChoice[];
  readonly latency: number;
  readonly source: 'clef' | 'heuristic';
  readonly heuristicChoice: string;
}

interface ChoiceAnswer {
  readonly choice: string;
  readonly confidence: number;
  readonly probabilities: Readonly<Record<string, number>>;
}

export class DecisionRequestError extends Error {}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

export function resolveSystemOneUrl(
  page: Pick<Document, 'baseURI' | 'querySelector'> = document,
): URL {
  const configured = page
    .querySelector<HTMLMetaElement>('meta[name="clef-api-path"]')
    ?.content.trim();
  return new URL(configured || 'v1/systemone', page.baseURI);
}

export function resolveModelName(
  page: Pick<Document, 'querySelector'> = document,
): string {
  const model = page
    .querySelector<HTMLMetaElement>('meta[name="clef-model-name"]')
    ?.content.trim();
  if (!model) {
    throw new DecisionRequestError('The CLEF model name is not configured.');
  }
  return model;
}

function parseAnswer(value: unknown, placements: readonly Placement[]): ChoiceAnswer {
  if (!isRecord(value) || !isRecord(value.answers)) {
    throw new DecisionRequestError('The model returned an invalid response.');
  }
  const move = value.answers.move;
  if (!isRecord(move)) {
    throw new DecisionRequestError('The model returned an invalid move.');
  }
  const rawProbabilities = move.probabilities;
  if (
    move.type !== 'choice' ||
    typeof move.choice !== 'string' ||
    typeof move.confidence !== 'number' ||
    !Number.isFinite(move.confidence) ||
    move.confidence < 0 ||
    move.confidence > 1 ||
    !isRecord(rawProbabilities)
  ) {
    throw new DecisionRequestError('The model returned an invalid move.');
  }

  const ids = new Set(placements.map(({ id }) => id));
  if (!ids.has(move.choice)) {
    throw new DecisionRequestError('The model selected an unavailable move.');
  }
  const probabilityIds = Object.keys(rawProbabilities);
  if (
    probabilityIds.length !== ids.size ||
    probabilityIds.some((id) => !ids.has(id))
  ) {
    throw new DecisionRequestError('The model returned invalid probabilities.');
  }
  const probabilities = Object.fromEntries(
    placements.map(({ id }) => {
      const probability = rawProbabilities[id];
      if (
        typeof probability !== 'number' ||
        !Number.isFinite(probability) ||
        probability < 0 ||
        probability > 1
      ) {
        throw new DecisionRequestError('The model returned invalid probabilities.');
      }
      return [id, probability];
    }),
  );
  const total = Object.values(probabilities).reduce(
    (sum, probability) => sum + probability,
    0,
  );
  const selectedProbability = probabilities[move.choice];
  if (
    Math.abs(total - 1) > 0.001 ||
    selectedProbability === undefined ||
    Math.abs(selectedProbability - move.confidence) > 0.001
  ) {
    throw new DecisionRequestError('The model returned invalid probabilities.');
  }
  return { choice: move.choice, confidence: move.confidence, probabilities };
}

export async function requestClefDecision(
  state: GameState,
  signal: AbortSignal,
  fetcher: typeof fetch = fetch,
  model: string = resolveModelName(),
): Promise<PolicyDecision> {
  const placements = enumeratePlacements(state);
  const heuristic = heuristicDecision(state);
  const started = performance.now();
  const response = await fetcher(resolveSystemOneUrl(), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(createDecisionRequest(state, model)),
    credentials: 'same-origin',
    signal,
  }).catch((error: unknown) => {
    if (error instanceof DOMException && error.name === 'AbortError') throw error;
    throw new DecisionRequestError('CLEF is unreachable. Check the runtime endpoint.');
  });

  if (!response.ok) {
    throw new DecisionRequestError(`CLEF request failed with status ${response.status}.`);
  }
  const body: unknown = await response.json().catch(() => {
    throw new DecisionRequestError('CLEF returned unreadable JSON.');
  });
  const answer = parseAnswer(body, placements);
  const ranked = placements
    .map((placement) => ({ placement, probability: answer.probabilities[placement.id] ?? 0 }))
    .sort((left, right) => right.probability - left.probability);

  return {
    choice: answer.choice,
    confidence: answer.confidence,
    ranked,
    latency: performance.now() - started,
    source: 'clef',
    heuristicChoice: heuristic.choice,
  };
}

function placementValue(placement: Placement): number {
  const { metrics } = placement;
  return (
    metrics.clearedLines * 8 -
    metrics.holes * 7 -
    metrics.aggregateHeight * 0.3 -
    metrics.maximumHeight * 0.5 -
    metrics.bumpiness * 0.2 -
    (placement.usedHold ? 0.05 : 0)
  );
}

export function heuristicDecision(state: GameState): PolicyDecision {
  const started = performance.now();
  const scored = enumeratePlacements(state)
    .map((placement) => ({ placement, value: placementValue(placement) }))
    .sort(
      (left, right) =>
        right.value - left.value || left.placement.id.localeCompare(right.placement.id),
    );
  const best = scored[0];
  if (best === undefined) throw new DecisionRequestError('No legal moves remain.');
  const maximum = best.value;
  const total = scored.reduce((sum, option) => sum + Math.exp(option.value - maximum), 0);
  const ranked = scored.map(({ placement, value }) => ({
    placement,
    probability: Math.exp(value - maximum) / total,
  }));

  return {
    choice: best.placement.id,
    confidence: ranked[0]?.probability ?? 1,
    ranked,
    latency: performance.now() - started,
    source: 'heuristic',
    heuristicChoice: best.placement.id,
  };
}
