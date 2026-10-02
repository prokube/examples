import { useEffect, useRef, useState } from 'react';

import {
  DecisionRequestError,
  heuristicDecision,
  requestClefDecision,
  type PolicyDecision,
} from './api';
import { Board, Controls, DecisionPanel, PiecePreview } from './components';
import {
  animationFrames,
  enumerateReachablePlacements,
  type AnimationFrame,
} from './game/animation';
import { applyPlacement, createGame } from './game/engine';
import { spawnColumn } from './game/board';

export function dateTimeSeed(date = new Date()) {
  const parts = [
    date.getFullYear(),
    date.getMonth() + 1,
    date.getDate(),
    date.getHours(),
    date.getMinutes(),
    date.getSeconds(),
  ];
  return parts
    .map((part, index) => String(part).padStart(index === 0 ? 4 : 2, '0'))
    .join('');
}

const DEFAULT_SEED = dateTimeSeed();

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
  readonly policyLocked?: boolean;
}

export function App({ initialMode = 'heuristic', policyLocked = false }: AppProps) {
  const [seed, setSeed] = useState(DEFAULT_SEED);
  const [game, setGame] = useState(() => createGame(Number(DEFAULT_SEED)));
  const [mode, setMode] = useState<'heuristic' | 'clef'>(initialMode);
  const [running, setRunning] = useState(true);
  const [speed, setSpeed] = useState(1);
  const [decision, setDecision] = useState<PolicyDecision | null>(null);
  const [animation, setAnimation] = useState<AnimationFrame | null>(null);
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
    const placements = enumerateReachablePlacements(game);
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

    const waitForResume = async () => {
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
      await waitForResume();
      if (!isCurrent()) return;
      const placement = placements.find(({ id }) => id === nextDecision.choice);
      if (placement === undefined) throw new DecisionRequestError('The policy selected an unavailable move.');
      setDecision(nextDecision);

      const frames = animationFrames(game.board, placement);
      if (frames === null) throw new DecisionRequestError('The selected move cannot be animated safely.');
      const first = frames[0];
      if (first === undefined) throw new DecisionRequestError('The selected move cannot be animated safely.');
      const startX = spawnColumn(placement.piece);
      const initialStatus = placement.rotation > 0
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
        if (frame.phase === 'position') setStatus('POSITIONING');
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
    const key = enumerateReachablePlacements(game)[0]?.id;
    if (key !== undefined) handled.current.delete(key);
    setError(null);
    setControl((value) => value + 1);
  };

  const changeMode = (next: 'heuristic' | 'clef') => {
    if (policyLocked || next === mode) return;
    operation.current += 1;
    activeOperation.current = null;
    const key = enumerateReachablePlacements(game)[0]?.id;
    if (key !== undefined) handled.current.delete(key);
    setDecision(null);
    setAnimation(null);
    setError(null);
    setStatus(runningRef.current ? 'READY' : 'PAUSED');
    setMode(next);
  };

  const currentStatus = game.gameOver ? 'GAME OVER' : status;

  return (
    <main className="app-shell">
      <header className="masthead">
        <div className="brand-mark" aria-hidden="true"><i /><i /><i /><i /></div>
        <div><span className="eyebrow">prokube.ai // decision lab 01</span><h1>STACK<br /> SIGNAL</h1></div>
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
          <DecisionPanel
            decision={decision}
            waiting={status === 'QUERYING CLEF' || status === 'SCORING OPTIONS'}
          />
          <Controls
            busy={animation !== null || status === 'QUERYING CLEF'}
            gameOver={game.gameOver}
            mode={mode}
            onModeChange={changeMode}
            onRestart={restart}
            onRunningChange={changeRunning}
            onSeedChange={setSeed}
            onSpeedChange={setSpeed}
            onStep={step}
            policyLocked={policyLocked}
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
