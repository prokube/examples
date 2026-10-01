# CLEF Tetris core

This package contains the framework-independent Tetris engine and the
SystemOne request mapping used by the CLEF-Flash demo. It intentionally has no
React or wall-clock dependencies and is consumed as source by the later Vite
application rather than published as a standalone Node package.

The engine uses a seeded seven-bag generator. At each turn it enumerates every
direct hard-drop placement for the active piece and, when available, the held
piece. It simulates each result and reports cleared lines, holes, aggregate
height, maximum height, and bumpiness. Rotation coordinates use normalized SRS
shape orientations because the policy selects final placements rather than
wall-kick paths. The visible 10x20 board is the complete simulation board, and
a blocked centered spawn position ends the game. Scoring uses the classic
single/double/triple/Tetris line-clear table without drop-distance bonuses.

```sh
npm ci
npm test
npm run typecheck
npm run lint
npm run build
```
