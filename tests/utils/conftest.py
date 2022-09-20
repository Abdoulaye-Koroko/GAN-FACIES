"""Common fixtures and check functions for tests/utils."""
import os
from typing import Tuple

import numpy as np
import pytest
import torch
from pytest_check import check_func
from torch.utils.data import DataLoader

from utils.configs import GlobalConfig
from utils.data.data_loader import DistributedDataLoader


class DataLoader64(DistributedDataLoader):
    """Data loader for unit tests (data size 64)."""

    def __init__(self) -> None:
        # pylint: disable=super-init-not-called
        self.n_classes = 4

    def loader(self) -> DataLoader:
        """Return pytorch data loader."""

        class Dataset64(torch.utils.data.Dataset):
            """Dataset for unit tests (data size 32)."""

            def __getitem__(self, index: int) -> Tuple[torch.Tensor, int]:
                return torch.randn(4, 64, 64), 0

            def __len__(self) -> int:
                return 10

        return torch.utils.data.DataLoader(dataset=Dataset64(),
                                           batch_size=2,
                                           shuffle=True,
                                           num_workers=0,
                                           )


class DataLoader32(DistributedDataLoader):
    """Data loader for unit tests (data size 32)."""

    def __init__(self) -> None:
        # pylint: disable=super-init-not-called
        self.n_classes = 4

    def loader(self) -> DataLoader:
        """Return pytorch data loader."""

        class Dataset32(torch.utils.data.Dataset):
            """Dataset for unit tests (data size 32)."""

            def __getitem__(self, index: int) -> Tuple[torch.Tensor, int]:
                return torch.randn(4, 32, 32), 0

            def __len__(self) -> int:
                return 10

        return torch.utils.data.DataLoader(dataset=Dataset32(),
                                           batch_size=2,
                                           shuffle=True,
                                           num_workers=0,
                                           )


@check_func
def check_allclose(arr1: np.ndarray, arr2: np.ndarray) -> None:
    """Check if two arrays are all close."""
    assert np.allclose(arr1, arr2)


@check_func
def check_exists(path: str) -> None:
    """Check if a path exists."""
    assert os.path.exists(path)


@pytest.fixture
def configs() -> Tuple[GlobalConfig, GlobalConfig]:
    """Return configs with data size 32 and 64."""
    config32 = GlobalConfig().build_from_argv(
        fallback='configs/unittest/data32.yaml')
    config64 = GlobalConfig().build_from_argv(
        fallback='configs/unittest/data64.yaml')
    return config32, config64
