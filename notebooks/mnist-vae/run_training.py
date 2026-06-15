import subprocess
import sys

# pytorch-lightning is not bundled in all notebook images — install if absent
try:
    import pytorch_lightning  # noqa: F401
except ImportError:
    subprocess.run(
        [sys.executable, "-m", "pip", "install", "-q", "pytorch-lightning"],
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
def run(hidden_dim: int, latent_dim: int) -> None:
    """
    Train a VAE model on the MNIST dataset using PyTorch Lightning.

    Args:
        hidden_dim (int): Dimension of the hidden layer.
        latent_dim (int): Dimension of the latent space.
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
        max_epochs=50,
        accelerator="gpu" if torch.cuda.is_available() else "cpu",
        devices=1,
        logger=logger,
    )

    # Start training
    trainer.fit(model=model, datamodule=dm)


if __name__ == "__main__":
    run()
