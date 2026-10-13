# Images
This folder contains code and Dockerfiles to create container images used elsewhere.

The [Build Images](../.github/workflows/build-images.yaml) workflow lists every
image in this repository with its build context. Each context has a `VERSION`
file with the image's version (`X.Y.Z` or `X.Y.Z-rcN`).

To release a changed image, bump its `VERSION` and update the references to
`europe-west3-docker.pkg.dev/prokube/releases/<image>:v<version>` in the same
pull request. Pull request checks fail when a reference does not match
`VERSION` and warn when an image's files change without a version bump. After
the merge to `main`, the workflow builds and pushes each image whose
`v<version>` tag does not exist in `prokube/releases` yet. Existing release
tags are immutable and never rebuilt.

Manual workflow runs publish commit and `latest` tags for all images to
`europe-west3-docker.pkg.dev/prokube/development`. Push manual test builds
there, not to `prokube/releases`.

Publishing requires the `GCP_SA_KEY` GitHub secret with access to the target
Google Artifact Registry repository.
