import os
import subprocess
import sys


def _cgroup_cpu_quota() -> int | None:
    """CPU core budget from the cgroup limit, or None if unset/unlimited."""
    try:
        with open("/sys/fs/cgroup/cpu.max") as fh:  # cgroup v2
            quota, period = fh.read().split()
        if quota == "max":
            return None
        return max(1, int(int(quota) / int(period)))
    except (FileNotFoundError, ValueError):
        pass
    try:  # cgroup v1
        with open("/sys/fs/cgroup/cpu/cpu.cfs_quota_us") as fh:
            quota = int(fh.read())
        if quota <= 0:
            return None
        with open("/sys/fs/cgroup/cpu/cpu.cfs_period_us") as fh:
            period = int(fh.read())
        return max(1, quota // period)
    except (FileNotFoundError, ValueError):
        return None


# torch/BLAS default their thread count to nproc (host core count), which can
# be far higher than the pod's actual cgroup CPU limit (e.g. 16 host cores vs
# a 4-CPU quota) — over-threading against a tight quota causes CFS throttling
# instead of faster training. Must be set before numpy/torch import to affect
# their BLAS thread pools; torch.set_num_threads() below covers torch itself.
_quota = _cgroup_cpu_quota()
if _quota is not None:
    os.environ.setdefault("OMP_NUM_THREADS", str(_quota))
    os.environ.setdefault("MKL_NUM_THREADS", str(_quota))

# Re-exec with Conda's libstdc++ so SciPy can resolve its CXXABI symbols.
_conda_lib = os.path.normpath(
    os.path.join(os.path.dirname(sys.executable), "..", "lib")
)
_ld = os.environ.get("LD_LIBRARY_PATH", "")
if os.path.isdir(_conda_lib) and _conda_lib not in _ld.split(os.pathsep):
    os.execvpe(
        sys.executable,
        [sys.executable] + sys.argv,
        {
            **os.environ,
            "LD_LIBRARY_PATH": os.pathsep.join(
                value for value in (_conda_lib, _ld) if value
            ),
        },
    )

# pytorch-lightning, torchvision, and tensorboard are not bundled in all notebook images
_missing = []
try:
    import pytorch_lightning  # noqa: F401
except ImportError:
    _missing.append("pytorch-lightning")
try:
    import torchvision  # noqa: F401
except ImportError:
    _missing.append("torchvision")
try:
    import tensorboard  # noqa: F401
except ImportError:
    _missing.append("tensorboard")
if _missing:
    subprocess.run(
        [sys.executable, "-m", "pip", "install", "-q"] + _missing,
        check=True,
    )

import click
import pytorch_lightning as pl
from pytorch_lightning.loggers import TensorBoardLogger
from model.vae import VAE
from model.datamodule import MNISTDataModule
import torch

if _quota is not None:
    torch.set_num_threads(_quota)


@click.command()
@click.option(
    "--hidden_dim", default=400, type=int, help="Dimension of the hidden layer."
)
@click.option(
    "--latent_dim", default=2, type=int, help="Dimension of the latent space."
)
@click.option("--max_epochs", default=50, type=int, help="Number of training epochs.")
def run(hidden_dim: int, latent_dim: int, max_epochs: int) -> None:
    """Train a VAE on MNIST."""

    # Initialize data module
    dm = MNISTDataModule(data_path="./data", num_workers=0, batch_size=32)
    dm.setup()

    # Initialize model
    model = VAE(
        input_dim=784,  # 28x28 pixels
        hidden_dim=hidden_dim,  # Dimension of the hidden layer
        latent_dim=latent_dim,  # Dimension of the latent space
    )

    # Initialize logger
    logger = TensorBoardLogger("tb_logs", name="mnist-vae")

    # Initialize trainer
    trainer = pl.Trainer(
        max_epochs=max_epochs,
        accelerator="gpu" if torch.cuda.is_available() else "cpu",
        devices=1,
        logger=logger,
    )

    # Start training
    trainer.fit(model=model, datamodule=dm)


if __name__ == "__main__":
    run()
