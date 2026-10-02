# CLEF Tetris decision lab

This package contains the responsive React application, framework-independent
Tetris engine, and SystemOne request mapping used by the CLEF-Flash demo. It can
run a complete deterministic game with the local heuristic policy or call a
CLEF SystemOne runtime once per piece.

The engine uses a seeded seven-bag generator. At each turn it enumerates every
direct hard-drop placement for the active piece and, when available, the held
piece. It simulates each result and reports cleared lines, holes, aggregate
height, maximum height, and bumpiness. Rotation coordinates use normalized SRS
shape orientations because the policy selects final placements rather than
wall-kick paths. The visible 10x20 board is the complete simulation board, and
a blocked centered spawn position ends the game. Scoring uses the classic
single/double/triple/Tetris line-clear table without drop-distance bonuses.

The application resolves the SystemOne endpoint relative to the document base
URL, so it works under arbitrary HTTP prefixes. At runtime, a host can replace
the `clef-api-path` meta tag in `index.html` with another relative path or a
fully qualified URL. The default is `v1/systemone`. The host must also set the
`clef-model-name` meta tag before enabling CLEF mode. The source leaves it blank
so deployments cannot silently send requests to a hardcoded model. No API key
is read or stored by the browser.

The container image serves the built application on port 8080 and proxies
`/v1/systemone` to `CLEF_UPSTREAM`, which defaults to
`clef-flash-predictor:80`. The image build sets the model name to `clef-flash`;
override the `CLEF_MODEL_NAME` build argument for another deployment. Set
`CLEF_POLICY` to `heuristic` or `clef` to choose and lock the deployed policy.

Build for the local Docker daemon or publish an amd64 image with Buildx:

```sh
make image TAG=dev
make image-push TAG=dev
```

```sh
npm ci
npm run dev
npm test
npm run typecheck
npm run lint
npm run build
```
