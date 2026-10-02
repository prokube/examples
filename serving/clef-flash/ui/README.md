# CLEF Tetris decision lab

This package contains the responsive React application, framework-independent
Tetris engine, and SystemOne request mapping used by the CLEF-Flash demo. It can
run a complete deterministic game with the local heuristic policy or call a
CLEF SystemOne runtime once per piece.

The engine uses a seeded seven-bag generator. At each turn it enumerates every
direct hard-drop placement for the active piece. Hold is intentionally omitted
to keep the SystemOne choice set bounded. The engine simulates each result and
reports cleared lines, holes, aggregate height, maximum height, and bumpiness.
Rotation coordinates use normalized SRS shape orientations because the policy
selects final placements rather than wall-kick paths. The visible 10x20 board
is the complete simulation board, and a blocked centered spawn position ends
the game. Scoring uses the classic single/double/triple/Tetris line-clear table
without drop-distance bonuses.

SystemOne receives every legal placement without heuristic filtering or
quality-based sorting. The shared state contains binary `.`/`#` boards for the
current position and every post-placement result, the next three pieces, and
the raw board metrics. Choice criteria remain compact and refer to those full
candidates by stable opaque IDs. No aggregate quality score is sent.

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
override the `CLEF_MODEL_NAME` build argument for another deployment. Leave
`CLEF_POLICY` empty to let users switch between the heuristic and the
decision model. Set it to `heuristic` or `clef` to choose and lock the deployed
policy; locked deployments hide the policy control.

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

For local CLEF development, forward the predictor and start Vite in separate
terminals:

```sh
kubectl -n llm-serving port-forward service/clef-flash-predictor 18080:80
VITE_CLEF_MODEL_NAME=clef-flash npm run dev
```

Vite proxies the relative `/v1/systemone` endpoint to
`CLEF_DEV_UPSTREAM`, which defaults to `http://127.0.0.1:18080`.
