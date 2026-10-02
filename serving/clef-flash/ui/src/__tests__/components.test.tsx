import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { App } from '../App';
import { heuristicDecision } from '../api';
import { Board, Controls, DecisionPanel } from '../components';
import {
  BOARD_HEIGHT,
  TETROMINOES,
  animationFrames,
  boardFromRows,
  canPlace,
  createGame,
  enumeratePlacements,
  enumerateReachablePlacements,
} from '../game';

function rows(row: string): readonly string[] {
  return [row, ...Array<string>(BOARD_HEIGHT - 1).fill('..........')];
}

function decisionResponse(body: string): Response {
  const request = JSON.parse(body) as {
    readonly questions: {
      readonly move: { readonly criteria: Readonly<Record<string, unknown>> };
    };
  };
  const ids = Object.keys(request.questions.move.criteria);
  const choice = ids[0];
  if (choice === undefined) throw new Error('Request has no choices');
  const probability = 1 / ids.length;
  return new Response(
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
  );
}

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

  it('routes around a blocked top-row path with legal single-step frames', () => {
    const game = {
      ...createGame(3),
      active: 'O' as const,
      board: boardFromRows(rows('...T......')),
      canHold: false,
    };
    const placement = enumeratePlacements(game).find(
      ({ piece, rotation, x }) => piece === 'O' && rotation === 0 && x === 0,
    );
    expect(placement).toBeDefined();
    if (placement === undefined) return;

    const frames = animationFrames(game.board, placement);
    expect(frames).not.toBeNull();
    if (frames === null) return;
    expect(
      frames.every((frame) =>
        canPlace(game.board, frame.piece, frame.rotation, frame.x, frame.y),
      ),
    ).toBe(true);
    for (let index = 1; index < frames.length; index += 1) {
      const previous = frames[index - 1];
      const frame = frames[index];
      expect(previous).toBeDefined();
      expect(frame).toBeDefined();
      if (previous === undefined || frame === undefined) continue;
      const horizontal =
        Math.abs(frame.x - previous.x) === 1 &&
        frame.y === previous.y &&
        frame.rotation === previous.rotation;
      const downward =
        frame.x === previous.x &&
        frame.y === previous.y + 1 &&
        frame.rotation === previous.rotation;
      const rotated =
        frame.x === previous.x &&
        frame.y === previous.y &&
        frame.rotation ===
          (previous.rotation + 1) % TETROMINOES[frame.piece].length;
      const dropStart =
        frame.phase === 'drop' &&
        frame.x === previous.x &&
        frame.y === previous.y &&
        frame.rotation === previous.rotation;
      expect(horizontal || downward || rotated || dropStart).toBe(true);
    }
    const dropRows = frames.filter(({ phase }) => phase === 'drop').map(({ y }) => y);
    expect(dropRows.at(-1)).toBe(placement.y);
  });

  it('excludes placements separated from spawn by a full-height wall', () => {
    const game = {
      ...createGame(4),
      active: 'O' as const,
      board: boardFromRows(Array<string>(BOARD_HEIGHT).fill('...T......')),
      canHold: false,
    };
    const placement = enumeratePlacements(game).find(
      ({ piece, rotation, x }) => piece === 'O' && rotation === 0 && x === 0,
    );
    expect(placement).toBeDefined();
    if (placement === undefined) return;

    expect(animationFrames(game.board, placement)).toBeNull();
    expect(
      enumerateReachablePlacements(game).some(({ id }) => id === placement.id),
    ).toBe(false);
  });

  it('shows the selected move, metrics, and all ranked probabilities', () => {
    const decision = heuristicDecision(createGame(2));
    const selected = decision.ranked.find(
      ({ placement }) => placement.id === decision.choice,
    );
    const { container } = render(<DecisionPanel decision={decision} />);
    const displayed = `${((selected?.probability ?? 0) * 100).toFixed(1)}%`;
    expect(screen.getByRole('list', { name: 'Ranked move probabilities' }).children).toHaveLength(decision.ranked.length);
    expect(screen.getByText('LOCAL HEURISTIC')).toBeInTheDocument();
    expect(screen.getByText('selected probability')).toBeInTheDocument();
    expect(container.querySelector('.confidence strong')).toHaveTextContent(displayed);
    expect(screen.getByRole('listitem', { current: true })).toHaveTextContent(
      displayed,
    );
  });

  it('keeps the latest decision visible while awaiting the next one', () => {
    const decision = heuristicDecision(createGame(2));
    render(<DecisionPanel decision={decision} waiting />);

    expect(screen.getByRole('status')).toHaveTextContent('Awaiting next decision');
    expect(screen.getByRole('list', { name: 'Ranked move probabilities' })).toBeInTheDocument();
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

  it('allows changing policy while a decision is busy', () => {
    const changeMode = vi.fn();
    render(<Controls busy gameOver={false} mode="heuristic" onModeChange={changeMode} onRestart={vi.fn()} onRunningChange={vi.fn()} onSeedChange={vi.fn()} onSpeedChange={vi.fn()} onStep={vi.fn()} running seed="42" speed={1} />);

    const clef = screen.getByRole('radio', { name: 'Decision Model' });
    expect(clef).toBeEnabled();
    fireEvent.click(clef);
    expect(changeMode).toHaveBeenCalledWith('clef');
  });

  it('locks policy when configured by the deployment', () => {
    render(<Controls busy={false} gameOver={false} mode="clef" onModeChange={vi.fn()} onRestart={vi.fn()} onRunningChange={vi.fn()} onSeedChange={vi.fn()} onSpeedChange={vi.fn()} onStep={vi.fn()} policyLocked running seed="42" speed={1} />);

    expect(screen.queryByRole('group', { name: 'Policy' })).not.toBeInTheDocument();
    expect(screen.queryByRole('radio', { name: 'Decision Model' })).not.toBeInTheDocument();
    expect(screen.queryByRole('radio', { name: 'Heuristic' })).not.toBeInTheDocument();
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

  it('does not advance a resolved CLEF decision while paused', async () => {
    const meta = document.createElement('meta');
    meta.name = 'clef-model-name';
    meta.content = 'configured-model';
    document.head.append(meta);
    let resolveRequest: ((response: Response) => void) | undefined;
    let requestBody = '';
    const fetcher = vi.fn(
      (_input: RequestInfo | URL, init?: RequestInit) =>
        new Promise<Response>((resolve) => {
          requestBody = String(init?.body ?? '');
          resolveRequest = resolve;
        }),
    );
    vi.stubGlobal('fetch', fetcher);

    render(<App initialMode="clef" />);
    await waitFor(() => expect(fetcher).toHaveBeenCalledOnce());
    fireEvent.click(screen.getByRole('button', { name: 'Pause' }));
    await act(async () => {
      resolveRequest?.(decisionResponse(requestBody));
      await new Promise((resolve) => window.setTimeout(resolve, 80));
    });

    expect(screen.getByText('PAUSED')).toBeInTheDocument();
    expect(screen.getByText('Awaiting first decision')).toBeInTheDocument();
    expect(screen.queryAllByLabelText(/block$/)).toHaveLength(0);
    fireEvent.click(screen.getByRole('button', { name: 'Resume' }));

    await waitFor(() =>
      expect(screen.queryByText('Awaiting first decision')).not.toBeInTheDocument(),
    );
    expect(fetcher).toHaveBeenCalledOnce();
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
    await act(async () => {
      replacement?.resolve(decisionResponse(replacement.body));
    });

    await waitFor(() => expect(screen.getByText('001')).toBeInTheDocument(), {
      timeout: 3000,
    });
  });

  it('removes the previous ranking immediately when restarting', async () => {
    const meta = document.createElement('meta');
    meta.name = 'clef-model-name';
    meta.content = 'configured-model';
    document.head.append(meta);
    const fetcher = vi.fn(
      (_input: RequestInfo | URL, init?: RequestInit) => {
        const body = String(init?.body ?? '');
        if (fetcher.mock.calls.length === 1) {
          return Promise.resolve(decisionResponse(body));
        }
        return new Promise<Response>(() => undefined);
      },
    );
    vi.stubGlobal('fetch', fetcher);

    render(<App initialMode="clef" />);
    await screen.findByText('selected probability');
    expect(screen.getByRole('list', { name: 'Ranked move probabilities' })).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Restart' }));

    await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(2));
    expect(screen.getByText('Awaiting first decision')).toBeInTheDocument();
    expect(screen.queryByRole('list', { name: 'Ranked move probabilities' })).not.toBeInTheDocument();
  });
});
