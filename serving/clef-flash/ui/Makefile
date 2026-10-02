IMAGE ?= europe-west3-docker.pkg.dev/prokube/development/clef-tetris-ui
TAG ?= dev
PLATFORM ?= linux/amd64

.PHONY: image image-push

image:
	docker buildx build --platform "$(PLATFORM)" --load --tag "$(IMAGE):$(TAG)" .

image-push:
	docker buildx build --platform "$(PLATFORM)" --push --tag "$(IMAGE):$(TAG)" .
