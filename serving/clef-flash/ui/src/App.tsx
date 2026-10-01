import { useEffect, useRef, useState } from 'react';

import {
  DecisionRequestError,
  heuristicDecision,
  requestClefDecision,
  type PolicyDecision,
} from './api';
import { Board, Controls, DecisionPanel, PiecePreview, type AnimatedPiece } from './components';
import { applyPlacement, createGame, enumeratePlacements } from './game/engine';
import { canPlace, spawnColumn } from './game/board';
import type { Board as BoardState, Placement } from './game/types';

const DEFAULT_SEED = '20261001';

function sleep(milliseconds: number, signal: AbortSignal) {
  return new Promise<void>((resolve, reject) => {
    const timer = window.setTimeout(resolve, milliseconds);
    signal.addEventListener('abort', () => {
      window.clearTimeout(timer);
      reject(new DOMException('Aborted', 'AbortError'));
    }, { once: true });
  });
}

interface AppProps {
  readonly initialMode?: 'heuristic' | 'clef';
}

function horizontalFrames(
  placement: Placement,
  rotation: number,
  startX: number,
): readonly AnimatedPiece[] {
  const direction = Math.sign(placement.x - startX);
  if (direction === 0) return [];
  const frames: AnimatedPiece[] = [];
  for (let x = startX + direction; x !== placement.x + direction; x += direction) {
    frames.push({ piece: placement.piece, rotation, x, y: 0, phase: 'move' });
  }
  return frames;
}

function rotationFrames(
  placement: Placement,
  x: number,
): readonly AnimatedPiece[] {
  return Array.from({ length: placement.rotation }, (_, index) => ({
    piece: placement.piece,
    rotation: index + 1,
    x,
    y: 0,
    phase: 'rotate' as const,
  }));
}

export function animationFrames(
  board: BoardState,
  placement: Placement,
): readonly AnimatedPiece[] {
  const startX = spawnColumn(placement.piece);
  const start: AnimatedPiece = {
    piece: placement.piece,
    rotation: 0,
    x: startX,
    y: 0,
    phase: 'rotate',
  };
  const routes = [
    [
      start,
      ...rotationFrames(placement, startX),
      ...horizontalFrames(placement, placement.rotation, startX),
    ],
    [
      start,
      ...horizontalFrames(placement, 0, startX),
      ...rotationFrames(placement, placement.x),
    ],
  ];
  const route = routes.find((frames) =>
    frames.every((frame) =>
      canPlace(board, frame.piece, frame.rotation, frame.x, frame.y),
    ),
  ) ?? [
    start,
    {
      piece: placement.piece,
      rotation: placement.rotation,
      x: placement.x,
      y: 0,
      phase: placement.rotation === 0 ? 'move' as const : 'rotate' as const,
    },
  ];
  const drop = Array.from({ length: placement.y + 1 }, (_, y) => ({
    piece: placement.piece,
    rotation: placement.rotation,
    x: placement.x,
    y,
    phase: 'drop' as const,
  }));
  return [...route, ...drop];
}

export function App({ initialMode = 'heuristic' }: AppProps) {
  const [seed, setSeed] = useState(DEFAULT_SEED);
  const [game, setGame] = useState(() => createGame(Number(DEFAULT_SEED)));
  const [mode, setMode] = useState<'heuristic' | 'clef'>(initialMode);
  const [running, setRunning] = useState(true);
  const [speed, setSpeed] = useState(1);
  const [decision, setDecision] = useState<PolicyDecision | null>(null);
  const [animation, setAnimation] = useState<AnimatedPiece | null>(null);
  const [status, setStatus] = useState('READY');
  const [error, setError] = useState<string | null>(null);
  const [control, setControl] = useState(0);
  const runningRef = useRef(running);
  const speedRef = useRef(speed);
  const stepping = useRef(false);
  const operation = useRef(0);
  const activeOperation = useRef<number | null>(null);
  const handled = useRef(new Set<string>());

  runningRef.current = running;
  speedRef.current = speed;

  useEffect(() => {
    if (game.gameOver || (!runningRef.current && !stepping.current)) return;
    const placements = enumeratePlacements(game);
    const key = placements[0]?.id;
    if (key === undefined || handled.current.has(key)) return;
    handled.current.add(key);
    const token = operation.current + 1;
    operation.current = token;
    activeOperation.current = token;
    const controller = new AbortController();
    const isCurrent = () => operation.current === token;

    const pauseAwareSleep = async (milliseconds: number) => {
      await sleep(milliseconds / speedRef.current, controller.signal);
      while (!runningRef.current && !stepping.current) {
        await sleep(40, controller.signal);
      }
    };

    const play = async () => {
      setError(null);
      setStatus(mode === 'clef' ? 'QUERYING CLEF' : 'SCORING OPTIONS');
      const nextDecision = mode === 'clef'
        ? await requestClefDecision(game, controller.signal)
        : heuristicDecision(game);
      if (!isCurrent()) return;
      const placement = placements.find(({ id }) => id === nextDecision.choice);
      if (placement === undefined) throw new DecisionRequestError('The policy selected an unavailable move.');
      setDecision(nextDecision);

      const frames = animationFrames(game.board, placement);
      const first = frames[0];
      if (first === undefined) throw new DecisionRequestError('The selected move cannot be animated safely.');
      const startX = spawnColumn(placement.piece);
      const initialStatus = placement.usedHold
        ? 'HOLD SWAP'
        : placement.rotation > 0
          ? 'ROTATING'
          : placement.x === startX
            ? 'HARD DROP'
            : placement.x < startX
              ? 'SHIFTING LEFT'
              : 'SHIFTING RIGHT';
      setStatus(initialStatus);
      setAnimation(first);
      await pauseAwareSleep(180);
      for (const frame of frames.slice(1)) {
        if (!isCurrent()) return;
        if (frame.phase === 'rotate') setStatus('ROTATING');
        if (frame.phase === 'move') {
          setStatus(placement.x < startX ? 'SHIFTING LEFT' : 'SHIFTING RIGHT');
        }
        if (frame.phase === 'drop') setStatus('HARD DROP');
        setAnimation(frame);
        await pauseAwareSleep(frame.phase === 'drop' ? 38 : 110);
      }

      if (!isCurrent()) return;
      await pauseAwareSleep(100);
      setAnimation(null);
      const next = applyPlacement(game, placement.id);
      setGame(next);
      if (stepping.current || next.gameOver) {
        stepping.current = false;
        runningRef.current = false;
        setRunning(false);
      }
      setStatus(next.gameOver ? 'GAME OVER' : runningRef.current ? 'NEXT PIECE' : 'PAUSED');
    };

    void play()
      .catch((cause: unknown) => {
        if (cause instanceof DOMException && cause.name === 'AbortError') return;
        if (!isCurrent()) return;
        const message = cause instanceof DecisionRequestError
          ? cause.message
          : 'The decision could not be applied safely.';
        handled.current.delete(key);
        runningRef.current = false;
        stepping.current = false;
        setRunning(false);
        setAnimation(null);
        setStatus('DECISION HALTED');
        setError(message);
      })
      .finally(() => {
        if (activeOperation.current === token) activeOperation.current = null;
      });

    return () => {
      if (operation.current === token) operation.current += 1;
      if (activeOperation.current === token) activeOperation.current = null;
      controller.abort();
    };
  }, [control, game, mode]);

  const changeRunning = (next: boolean) => {
    runningRef.current = next;
    setRunning(next);
    setStatus(next ? 'RESUMING' : 'PAUSED');
    if (next) setError(null);
    if (next && activeOperation.current === null) {
      setControl((value) => value + 1);
    }
  };

  const restart = () => {
    const parsed = Number(seed);
    const nextSeed = Number.isSafeInteger(parsed) ? parsed : Number(DEFAULT_SEED);
    operation.current += 1;
    activeOperation.current = null;
    handled.current.clear();
    stepping.current = false;
    runningRef.current = true;
    setRunning(true);
    setDecision(null);
    setAnimation(null);
    setError(null);
    setStatus('READY');
    setGame(createGame(nextSeed));
  };

  const step = () => {
    stepping.current = true;
    const key = enumeratePlacements(game)[0]?.id;
    if (key !== undefined) handled.current.delete(key);
    setError(null);
    setControl((value) => value + 1);
  };

  const currentStatus = game.gameOver ? 'GAME OVER' : status;

  return (
    <main className="app-shell">
      <header className="masthead">
        <div className="brand-mark" aria-hidden="true"><i /><i /><i /><i /></div>
        <div><span className="eyebrow">prokube.ai // decision lab 01</span><h1>STACK<br />SIGNAL</h1></div>
        <div className="live-status"><span className={error === null ? 'pulse' : 'pulse pulse--error'} />{currentStatus}</div>
      </header>

      {error !== null && (
        <div className="error-banner" role="alert">
          <div><span className="eyebrow">Policy failure</span><strong>{error}</strong></div>
          <button className="button" onClick={step}>Retry one decision</button>
        </div>
      )}

      <div className="game-layout">
        <aside className="game-stats panel">
          <div><span className="eyebrow">Score</span><strong>{game.stats.score.toLocaleString()}</strong></div>
          <div><span className="eyebrow">Lines</span><strong>{String(game.stats.lines).padStart(2, '0')}</strong></div>
          <div><span className="eyebrow">Level</span><strong>{String(game.stats.level).padStart(2, '0')}</strong></div>
          <div><span className="eyebrow">Pieces</span><strong>{String(game.stats.pieces).padStart(3, '0')}</strong></div>
          <PiecePreview label="Hold" piece={game.hold} />
        </aside>

        <section className="board-stage">
          <div className="board-frame">
            <div className="board-label"><span>PLAYFIELD / 10×20</span><span>SEED {game.seed}</span></div>
            <Board active={animation} board={game.board} />
          </div>
          <div className="queue-strip panel">
            <PiecePreview label="Next" piece={game.queue[0] ?? null} />
            <div className="queue-list"><span className="eyebrow">Queue</span><strong>{game.queue.slice(1, 5).join('  ')}</strong></div>
          </div>
        </section>

        <div className="right-rail">
          <DecisionPanel decision={decision} />
          <Controls
            busy={animation !== null || status === 'QUERYING CLEF'}
            gameOver={game.gameOver}
            mode={mode}
            onModeChange={setMode}
            onRestart={restart}
            onRunningChange={changeRunning}
            onSeedChange={setSeed}
            onSpeedChange={setSpeed}
            onStep={step}
            running={running}
            seed={seed}
            speed={speed}
          />
        </div>
      </div>
      <footer><span>ONE REQUEST / PIECE</span><span>DETERMINISTIC PHYSICS</span><span>BOUNDED DECISIONS</span></footer>
    </main>
  );
}
