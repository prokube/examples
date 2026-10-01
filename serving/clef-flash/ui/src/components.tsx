import type { CSSProperties } from 'react';

import type { PolicyDecision } from './api';
import type { AnimationFrame } from './game/animation';
import { placementCells } from './game/board';
import { orientation } from './game/tetrominoes';
import {
  BOARD_HEIGHT,
  BOARD_WIDTH,
  type Board as BoardState,
  type PieceType,
  type Placement,
} from './game/types';

interface BoardProps {
  readonly board: BoardState;
  readonly active: AnimationFrame | null;
}

export function Board({ board, active }: BoardProps) {
  const overlay = new Map(
    active
      ? placementCells(active.piece, active.rotation, active.x, active.y).map(
          ({ x, y }) => [`${x}:${y}`, active.piece] as const,
        )
      : [],
  );

  return (
    <div
      className={`board ${active?.phase === 'drop' ? 'board--dropping' : ''}`}
      aria-label="Tetris board"
      aria-colcount={BOARD_WIDTH}
      aria-rowcount={BOARD_HEIGHT}
      role="grid"
      style={{ '--rows': BOARD_HEIGHT, '--columns': BOARD_WIDTH } as CSSProperties}
    >
      {board.map((row, y) => (
        <div aria-rowindex={y + 1} className="board__row" key={y} role="row">
          {row.map((cell, x) => {
            const piece = overlay.get(`${x}:${y}`) ?? cell;
            return (
              <span
                aria-colindex={x + 1}
                aria-label={piece === null ? 'Empty' : `${piece} block`}
                className={`cell ${piece === null ? '' : `cell--${piece}`} ${overlay.has(`${x}:${y}`) ? 'cell--active' : ''}`}
                key={`${x}:${y}`}
                role="gridcell"
              />
            );
          })}
        </div>
      ))}
    </div>
  );
}

export function PiecePreview({ piece, label }: { readonly piece: PieceType | null; readonly label: string }) {
  const cells = piece === null ? [] : orientation(piece, 0);
  const occupied = new Set(cells.map(({ x, y }) => `${x}:${y}`));
  return (
    <div className="preview-wrap">
      <span className="eyebrow">{label}</span>
      <div className="preview" aria-label={`${label}: ${piece ?? 'empty'}`}>
        {Array.from({ length: 8 }, (_, index) => {
          const x = index % 4;
          const y = Math.floor(index / 4);
          return <i className={occupied.has(`${x}:${y}`) ? `cell--${piece}` : ''} key={index} />;
        })}
      </div>
      <strong>{piece ?? '—'}</strong>
    </div>
  );
}

function moveName(placement: Placement) {
  const hold = placement.usedHold ? 'hold · ' : '';
  return `${hold}${placement.piece} / R${placement.rotation} / C${placement.x + 1}`;
}

export function DecisionPanel({ decision }: { readonly decision: PolicyDecision | null }) {
  const selected = decision?.ranked.find(({ placement }) => placement.id === decision.choice);
  if (decision === null || selected === undefined) {
    return (
      <section className="decision panel" aria-labelledby="decision-heading">
        <header><span className="eyebrow">Decision stream</span><h2 id="decision-heading">Awaiting first signal</h2></header>
        <p className="muted">Candidate probabilities and board outcomes appear here after policy evaluation.</p>
      </section>
    );
  }
  const metrics = selected.placement.metrics;
  return (
    <section className="decision panel" aria-labelledby="decision-heading">
      <header className="decision__header">
        <div>
          <span className="eyebrow">Selected move</span>
          <h2 id="decision-heading">{moveName(selected.placement)}</h2>
        </div>
        <div className="confidence"><strong>{Math.round(decision.confidence * 100)}%</strong><span>confidence</span></div>
      </header>
      <div className="metrics" aria-label="Selected move metrics">
        <span><b>{metrics.clearedLines}</b> clears</span>
        <span><b>{metrics.holes}</b> holes</span>
        <span><b>{metrics.aggregateHeight}</b> height</span>
        <span><b>{metrics.maximumHeight}</b> max</span>
        <span><b>{metrics.bumpiness}</b> bump</span>
      </div>
      <div className="decision__meta">
        <span>{decision.source === 'clef' ? 'CLEF RUNTIME' : 'LOCAL HEURISTIC'}</span>
        <span>{decision.latency.toFixed(decision.latency < 10 ? 2 : 0)} ms</span>
        {decision.source === 'clef' && <span>{decision.choice === decision.heuristicChoice ? 'agrees with heuristic' : 'diverges from heuristic'}</span>}
      </div>
      <ol className="ranking" aria-label="Ranked move probabilities">
        {decision.ranked.map(({ placement, probability }, index) => (
          <li className={placement.id === decision.choice ? 'ranking__selected' : ''} key={placement.id}>
            <span className="ranking__index">{String(index + 1).padStart(2, '0')}</span>
            <span className="ranking__move">{moveName(placement)}</span>
            <span className="ranking__bar"><i style={{ width: `${probability * 100}%` }} /></span>
            <strong>{(probability * 100).toFixed(1)}%</strong>
          </li>
        ))}
      </ol>
    </section>
  );
}

interface ControlsProps {
  readonly running: boolean;
  readonly busy: boolean;
  readonly gameOver: boolean;
  readonly mode: 'heuristic' | 'clef';
  readonly speed: number;
  readonly seed: string;
  readonly onRunningChange: (running: boolean) => void;
  readonly onStep: () => void;
  readonly onRestart: () => void;
  readonly onModeChange: (mode: 'heuristic' | 'clef') => void;
  readonly onSpeedChange: (speed: number) => void;
  readonly onSeedChange: (seed: string) => void;
}

export function Controls(props: ControlsProps) {
  return (
    <section className="controls panel" aria-label="Game controls">
      <div className="control-group">
        <span className="eyebrow">Transport</span>
        <div className="button-row">
          <button className="button button--primary" disabled={props.gameOver} onClick={() => props.onRunningChange(!props.running)}>
            {props.gameOver ? 'Game over' : props.running ? 'Pause' : 'Resume'}
          </button>
          <button className="button" disabled={props.gameOver || props.running || props.busy} onClick={props.onStep}>Single step</button>
          <button className="button" onClick={props.onRestart}>Restart</button>
        </div>
      </div>
      <fieldset className="control-group" disabled={props.busy}>
        <legend className="eyebrow">Policy</legend>
        <div className="segmented">
          <label><input checked={props.mode === 'heuristic'} name="policy" onChange={() => props.onModeChange('heuristic')} type="radio" />Heuristic</label>
          <label><input checked={props.mode === 'clef'} name="policy" onChange={() => props.onModeChange('clef')} type="radio" />CLEF</label>
        </div>
      </fieldset>
      <label className="control-group range">
        <span className="eyebrow">Animation speed <b>{props.speed}×</b></span>
        <input max="4" min="0.5" onChange={(event) => props.onSpeedChange(Number(event.target.value))} step="0.5" type="range" value={props.speed} />
      </label>
      <label className="control-group seed">
        <span className="eyebrow">Deterministic seed</span>
        <input inputMode="numeric" onChange={(event) => props.onSeedChange(event.target.value)} type="number" value={props.seed} />
      </label>
    </section>
  );
}
