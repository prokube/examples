"""
Monkey patches for KFP DockerRunner to enable port mapping and environment variable support.

This module patches older versions of KFP that don't have built-in port/environment support
to match the upstream 2.14+ API. Import this module BEFORE using DockerRunner with ports/environment.

Usage (exactly like upstream KFP 2.14+):
    from utils import kfp_docker_monkey_patches  # noqa: F401 — Apply patches on import
    from kfp import local

    # Explicit ports and environment (upstream-compatible API)
    local.init(runner=local.DockerRunner(
        ports={'5678/tcp': 5678},
        environment={'KFP_DEBUG': 'true', 'MY_VAR': 'value'}
    ))
"""

from kfp import local
from kfp.local import docker_task_handler
from kfp.local.config import DockerRunner
import docker
from loguru import logger


def apply_docker_port_patches():
    """Apply all necessary patches to enable port support in DockerRunner."""

    # Patch 1: Enable ports argument in DockerRunner
    _patch_docker_runner_args()

    # Patch 2: Extend run_docker_container to accept additional arguments
    _patch_run_docker_container()

    # Patch 3: Modify DockerTaskHandler to pass through container arguments
    _patch_docker_task_handler()

    # Patch 4: Extend DockerRunner constructor
    _patch_docker_runner_init()


def _patch_docker_runner_args():
    """Add ports and environment to allowed DockerRunner arguments."""
    if not hasattr(DockerRunner, "DOCKER_CONTAINER_RUN_ARGS"):
        # Create set with essential arguments including ports and environment for older versions
        DockerRunner.DOCKER_CONTAINER_RUN_ARGS = {
            "ports",
            "environment",
            "volumes",
            "network_mode",
            "user",
            "working_dir",
            "entrypoint",
            "command",
            "auto_remove",
            "privileged",
        }
    else:
        # Add ports and environment to existing set
        DockerRunner.DOCKER_CONTAINER_RUN_ARGS.add("ports")
        DockerRunner.DOCKER_CONTAINER_RUN_ARGS.add("environment")


def _patch_run_docker_container():
    """Patch run_docker_container to accept additional Docker arguments."""

    # Backup original function
    original_run_docker_container = docker_task_handler.run_docker_container

    def patched_run_docker_container(client, image, command, volumes, **kwargs):
        """Enhanced run_docker_container with support for additional Docker arguments."""

        # Add latest tag if not present
        if ":" not in image:
            image = f"{image}:latest"

        # Check if image exists
        image_exists = any(
            image in existing_image.tags for existing_image in client.images.list()
        )

        if image_exists:
            print(f"Found image {image!r}\n")
        else:
            print(f"Pulling image {image!r}")
            repository, tag = image.rsplit(":", 1)
            client.images.pull(repository=repository, tag=tag)
            print("Image pull complete\n")

        # Run container with all provided arguments
        container = client.containers.run(
            image=image,
            command=command,
            detach=True,
            stdout=True,
            stderr=True,
            volumes=volumes,
            **kwargs,  # Pass through ports and other arguments
        )

        # Stream logs
        for line in container.logs(stream=True):
            print(line.decode(), end="")

        return container.wait()["StatusCode"]

    # Replace original function
    docker_task_handler.run_docker_container = patched_run_docker_container


def _patch_docker_task_handler():
    """Patch DockerTaskHandler to pass container arguments to run_docker_container."""

    # Backup original method
    original_docker_task_handler_run = docker_task_handler.DockerTaskHandler.run

    def patched_docker_task_handler_run(self):
        """Enhanced DockerTaskHandler.run method with container args support."""
        import docker

        client = docker.from_env()
        try:
            volumes = self.get_volumes_to_mount()

            # Get additional container arguments from runner
            extra_args = {}
            if hasattr(self.runner, "container_run_args"):
                extra_args = dict(self.runner.container_run_args)
            elif hasattr(self.runner, "__dict__"):
                # Fallback: only forward keys that are valid Docker container.run() args
                allowed = getattr(DockerRunner, "DOCKER_CONTAINER_RUN_ARGS", set())
                extra_args = {
                    k: v for k, v in self.runner.__dict__.items() if k in allowed
                }

            if "volumes" in extra_args:
                user_volumes = extra_args.pop("volumes")
                volumes.update(user_volumes)
            return_code = docker_task_handler.run_docker_container(
                client=client,
                image=self.image,
                command=self.full_command,
                volumes=volumes,
                **extra_args,
            )
        finally:
            client.close()

        from kfp.local import status

        return status.Status.SUCCESS if return_code == 0 else status.Status.FAILURE

    # Replace original method
    docker_task_handler.DockerTaskHandler.run = patched_docker_task_handler_run


def _patch_docker_runner_init():
    """Patch DockerRunner constructor to store container arguments."""

    # Backup original init (if it exists)
    original_docker_runner_init = getattr(DockerRunner, "__init__", None)

    def patched_docker_runner_init(self, **kwargs):
        """Enhanced DockerRunner constructor that stores container run arguments."""
        import os

        # Call original __init__ if it exists
        if original_docker_runner_init is not None:
            try:
                original_docker_runner_init(self)
            except TypeError:
                pass  # Original init may not accept extra args

        # Auto-pass debug environment variables to container
        environment = kwargs.get("environment", {})
        if "KFP_DEBUG" not in environment and "KFP_DEBUG" in os.environ:
            environment["KFP_DEBUG"] = os.environ["KFP_DEBUG"]
        if "KFP_DEBUG_PORT" not in environment and "KFP_DEBUG_PORT" in os.environ:
            environment["KFP_DEBUG_PORT"] = os.environ["KFP_DEBUG_PORT"]

        if environment:
            kwargs["environment"] = environment

        # Store container run args for later use
        self.container_run_args = kwargs

        # Call original __post_init__ if it exists (for dataclass compatibility)
        if hasattr(DockerRunner, "__post_init__"):
            self.__post_init__()

    # Replace constructor
    DockerRunner.__init__ = patched_docker_runner_init


# Apply patches immediately when module is imported
apply_docker_port_patches()

logger.info("KFP Docker port & environment patches applied successfully")
logger.debug(
    "Usage (upstream 2.14+ compatible): DockerRunner(ports={'5678/tcp': 5678}, environment={'DEBUG': 'true'})"
)
logger.debug("This patch will be obsolete once you upgrade to KFP 2.14+")
