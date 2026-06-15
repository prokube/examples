import os
import subprocess
import sys

# Re-exec with conda's libstdc++ prepended to LD_LIBRARY_PATH when needed.
# scipy 1.17+ requires CXXABI_1.3.15 which the system libstdc++ may lack; the
# conda-bundled libstdc++ provides it. LD_LIBRARY_PATH must be set before the
# process starts (the dynamic linker reads it once), so we re-exec if the
# conda lib dir is not already in the path.
_conda_lib = os.path.normpath(
    os.path.join(os.path.dirname(sys.executable), "..", "lib")
)
_ld = os.environ.get("LD_LIBRARY_PATH", "")
if os.path.isdir(_conda_lib) and _conda_lib not in _ld.split(":"):
    os.execvpe(
        sys.executable,
        [sys.executable] + sys.argv,
        {**os.environ, "LD_LIBRARY_PATH": f"{_conda_lib}:{_ld}"},
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


@click.command()
@click.option(
    "--hidden_dim", default=400, type=int, help="Dimension of the hidden layer."
)
@click.option(
    "--latent_dim", default=2, type=int, help="Dimension of the latent space."
)
@click.option("--max_epochs", default=50, type=int, help="Number of training epochs.")
def run(hidden_dim: int, latent_dim: int, max_epochs: int) -> None:
    """
    Train a VAE model on the MNIST dataset using PyTorch Lightning.

    Args:
        hidden_dim (int): Dimension of the hidden layer.
        latent_dim (int): Dimension of the latent space.
        max_epochs (int): Number of training epochs.
    """

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
