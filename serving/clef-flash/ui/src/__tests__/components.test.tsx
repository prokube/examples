import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { App, animationFrames } from '../App';
import { heuristicDecision } from '../api';
import { Board, Controls, DecisionPanel } from '../components';
import { applyPlacement, canPlace, createGame, enumeratePlacements } from '../game';

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  document.head
    .querySelectorAll('meta[name="clef-model-name"]')
    .forEach((meta) => meta.remove());
});

describe('game interface components', () => {
  it('renders the complete board and active piece accessibly', () => {
    const game = createGame(1);
    render(<Board active={{ piece: 'T', rotation: 0, x: 3, y: 0, phase: 'rotate' }} board={game.board} />);
    expect(screen.getAllByRole('row')).toHaveLength(20);
    expect(screen.getAllByRole('gridcell')).toHaveLength(200);
    expect(screen.getAllByLabelText('T block')).toHaveLength(4);
  });

  it('keeps every animation frame collision-free and drops row by row', () => {
    let game = createGame(3);
    for (let turn = 0; turn < 1329; turn += 1) {
      game = applyPlacement(game, heuristicDecision(game).choice);
    }
    const choice = heuristicDecision(game).choice;
    const placement = enumeratePlacements(game).find(({ id }) => id === choice);
    expect(placement).toBeDefined();
    if (placement === undefined) return;

    const frames = animationFrames(game.board, placement);
    expect(
      frames.every((frame) =>
        canPlace(game.board, frame.piece, frame.rotation, frame.x, frame.y),
      ),
    ).toBe(true);
    expect(frames.filter(({ phase }) => phase === 'drop').map(({ y }) => y)).toEqual(
      Array.from({ length: placement.y + 1 }, (_, y) => y),
    );
  });

  it('shows the selected move, metrics, and all ranked probabilities', () => {
    const decision = heuristicDecision(createGame(2));
    render(<DecisionPanel decision={decision} />);
    expect(screen.getByRole('list', { name: 'Ranked move probabilities' }).children).toHaveLength(decision.ranked.length);
    expect(screen.getByText('LOCAL HEURISTIC')).toBeInTheDocument();
    expect(screen.getByText('confidence')).toBeInTheDocument();
  });

  it('provides pause, step, restart, speed, seed, and policy controls', () => {
    const pause = vi.fn();
    render(<Controls busy={false} gameOver={false} mode="heuristic" onModeChange={vi.fn()} onRestart={vi.fn()} onRunningChange={pause} onSeedChange={vi.fn()} onSpeedChange={vi.fn()} onStep={vi.fn()} running seed="42" speed={1} />);
    fireEvent.click(screen.getByRole('button', { name: 'Pause' }));
    expect(pause).toHaveBeenCalledWith(false);
    expect(screen.getByRole('button', { name: 'Single step' })).toBeDisabled();
    expect(screen.getByDisplayValue('42')).toBeInTheDocument();
  });

  it('disables transport controls when the game is over', () => {
    render(<Controls busy={false} gameOver mode="heuristic" onModeChange={vi.fn()} onRestart={vi.fn()} onRunningChange={vi.fn()} onSeedChange={vi.fn()} onSpeedChange={vi.fn()} onStep={vi.fn()} running={false} seed="42" speed={1} />);

    expect(screen.getByRole('button', { name: 'Game over' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Single step' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Restart' })).toBeEnabled();
  });

  it('pauses safely and displays CLEF network failures', async () => {
    const meta = document.createElement('meta');
    meta.name = 'clef-model-name';
    meta.content = 'configured-model';
    document.head.append(meta);
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('network error')));

    render(<App initialMode="clef" />);

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'CLEF is unreachable. Check the runtime endpoint.',
    );
    expect(screen.getByRole('button', { name: 'Resume' })).toBeInTheDocument();

  });

  it('pauses safely and displays invalid CLEF responses', async () => {
    const meta = document.createElement('meta');
    meta.name = 'clef-model-name';
    meta.content = 'configured-model';
    document.head.append(meta);
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ answers: { move: null } }), { status: 200 }),
      ),
    );

    render(<App initialMode="clef" />);

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'The model returned an invalid move.',
    );
    expect(screen.getByRole('button', { name: 'Resume' })).toBeInTheDocument();

  });

  it('retries a failed decision when transport is resumed', async () => {
    const meta = document.createElement('meta');
    meta.name = 'clef-model-name';
    meta.content = 'configured-model';
    document.head.append(meta);
    const fetcher = vi.fn()
      .mockRejectedValueOnce(new TypeError('network error'))
      .mockRejectedValueOnce(new TypeError('network error'));
    vi.stubGlobal('fetch', fetcher);

    render(<App initialMode="clef" />);
    await screen.findByRole('alert');
    fireEvent.click(screen.getByRole('button', { name: 'Resume' }));

    await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(2));
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'CLEF is unreachable. Check the runtime endpoint.',
    );
  });

  it('does not let an aborted restart operation clear the replacement operation', async () => {
    const meta = document.createElement('meta');
    meta.name = 'clef-model-name';
    meta.content = 'configured-model';
    document.head.append(meta);
    const pending: Array<{
      readonly body: string;
      readonly resolve: (response: Response) => void;
    }> = [];
    const fetcher = vi.fn(
      (_input: RequestInfo | URL, init?: RequestInit) =>
        new Promise<Response>((resolve, reject) => {
          init?.signal?.addEventListener(
            'abort',
            () => reject(new DOMException('Aborted', 'AbortError')),
            { once: true },
          );
          pending.push({ body: String(init?.body ?? ''), resolve });
        }),
    );
    vi.stubGlobal('fetch', fetcher);

    render(<App initialMode="clef" />);
    await waitFor(() => expect(fetcher).toHaveBeenCalledOnce());
    fireEvent.click(screen.getByRole('button', { name: 'Restart' }));
    await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(2));
    await Promise.resolve();

    fireEvent.change(screen.getByRole('slider'), { target: { value: '4' } });
    fireEvent.click(screen.getByRole('button', { name: 'Pause' }));
    fireEvent.click(screen.getByRole('button', { name: 'Resume' }));
    const replacement = pending[1];
    expect(replacement).toBeDefined();
    const request = JSON.parse(replacement?.body ?? '{}') as {
      readonly questions: {
        readonly move: { readonly criteria: Readonly<Record<string, unknown>> };
      };
    };
    const ids = Object.keys(request.questions.move.criteria);
    const choice = ids[0];
    expect(choice).toBeDefined();
    const probability = 1 / ids.length;
    await act(async () => {
      replacement?.resolve(
        new Response(
          JSON.stringify({
            answers: {
              move: {
                type: 'choice',
                choice,
                confidence: probability,
                probabilities: Object.fromEntries(ids.map((id) => [id, probability])),
              },
            },
          }),
          { status: 200 },
        ),
      );
    });

    await waitFor(() => expect(screen.getByText('001')).toBeInTheDocument(), {
      timeout: 3000,
    });
  });
});
