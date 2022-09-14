"""Tests for utils/gan/uncond_sagan/trainer.py."""

import os
import shutil
from typing import Tuple

import numpy as np
import pytest_check as check
import torch
from pytest_mock import MockerFixture

from utils.configs import GlobalConfig
from utils.gan.uncond_sagan.modules import (UncondSADiscriminator,
                                            UncondSAGenerator)
from utils.gan.uncond_sagan.trainer import UncondTrainerSAGAN


def test_train_generator(mocker: MockerFixture,
                         configs: Tuple[GlobalConfig, GlobalConfig]) -> None:
    """Test train_generator method."""
    _, config64 = configs
    data_loader = mocker.MagicMock(n_classes=4)
    trainer = UncondTrainerSAGAN(data_loader=data_loader, config=config64)
    trainer.step = 0  # start EMA
    os.makedirs('res/tmp_test/models/', exist_ok=True)
    gen = UncondSAGenerator(4, config64.model).to("cuda:0")
    disc = UncondSADiscriminator(4, config64.model).to("cuda:0")
    g_optimizer = torch.optim.Adam(gen.parameters(), lr=0.0002)
    data = torch.rand(2, 4, 64, 64)
    gen, g_optimizer, losses = trainer.train_generator(
        gen=gen, g_optimizer=g_optimizer, disc=disc,
        real_batch=(data,), device="cuda:0")
    check.is_instance(gen, UncondSAGenerator)
    check.is_instance(g_optimizer, torch.optim.Adam)
    check.equal(losses.keys(), {"g_loss"})
    for loss in losses.values():
        check.is_instance(loss, tuple)
        check.equal(len(loss), 3)
        check.is_instance(loss[0], torch.Tensor)
        check.equal(loss[0].shape, tuple())
        check.is_instance(loss[1], str)
        check.is_instance(loss[2], int)

    # Test with Hinge loss and without mixed precision
    config64_bis = config64.copy()
    config64_bis.merge({"training": {"adv_loss": "hinge",
                                     "mixed_precision": False}},
                       do_not_pre_process=True)
    trainer = UncondTrainerSAGAN(data_loader=data_loader, config=config64_bis)
    gen, g_optimizer, losses = trainer.train_generator(
        gen=gen, g_optimizer=g_optimizer, disc=disc,
        real_batch=(data,), device="cuda:0")

    shutil.rmtree('res/tmp_test/models/')


def test_train_discriminator(mocker: MockerFixture,
                             configs: Tuple[GlobalConfig, GlobalConfig]
                             ) -> None:
    """Test train_generator method."""
    _, config64 = configs
    data_loader = mocker.MagicMock(n_classes=4)
    trainer = UncondTrainerSAGAN(data_loader=data_loader, config=config64)
    trainer.step = 0  # start EMA
    os.makedirs('res/tmp_test/models/', exist_ok=True)
    gen = UncondSAGenerator(4, config64.model).to("cuda:0")
    disc = UncondSADiscriminator(4, config64.model).to("cuda:0")
    d_optimizer = torch.optim.Adam(disc.parameters(), lr=0.0002)
    data = torch.rand(2, 4, 64, 64)
    disc, d_optimizer, losses = trainer.train_discriminator(
        disc=disc, d_optimizer=d_optimizer, gen=gen,
        real_batch=(data,), device="cuda:0")
    check.is_instance(disc, UncondSADiscriminator)
    check.is_instance(d_optimizer, torch.optim.Adam)
    check.equal(losses.keys(), {"d_loss", "d_loss_real", "d_loss_gp"})
    for loss in losses.values():
        check.is_instance(loss, tuple)
        check.equal(len(loss), 3)
        check.is_instance(loss[0], torch.Tensor)
        check.equal(loss[0].shape, tuple())
        check.is_instance(loss[1], str)
        check.is_instance(loss[2], int)

    # Test with Hinge loss and without mixed precision
    config64_bis = config64.copy()
    config64_bis.merge({"training": {"adv_loss": "hinge",
                                     "mixed_precision": False}},
                       do_not_pre_process=True)
    trainer = UncondTrainerSAGAN(data_loader=data_loader, config=config64_bis)
    _, _, losses = trainer.train_discriminator(
        disc=disc, d_optimizer=d_optimizer, gen=gen,
        real_batch=(data,), device="cuda:0")
    check.is_not_in("d_loss_gp", losses.keys())

    shutil.rmtree('res/tmp_test/models/')


def test_build_model_opt(mocker: MockerFixture,
                         configs: Tuple[GlobalConfig, GlobalConfig]) -> None:
    """Test build_model_opt."""
    _, config64 = configs
    data_loader = mocker.MagicMock(n_classes=4)
    trainer = UncondTrainerSAGAN(data_loader=data_loader, config=config64)
    gen, disc, g_optimizer, d_optimizer = trainer.build_model_opt()
    check.is_instance(gen, UncondSAGenerator)
    check.is_instance(disc, UncondSADiscriminator)
    check.is_instance(g_optimizer, torch.optim.Adam)
    check.is_instance(d_optimizer, torch.optim.Adam)

    # Test with recovering from step
    os.makedirs('res/tmp_test/models/', exist_ok=True)
    torch.save(gen.state_dict(),
               'res/tmp_test/models/generator_step_8.pth')
    torch.save(disc.state_dict(),
               'res/tmp_test/models/discriminator_step_8.pth')
    config64_bis = config64.copy()
    config64_bis.merge({"recover_model_step": 8},
                       do_not_pre_process=True)
    trainer = UncondTrainerSAGAN(data_loader=data_loader,
                                 config=config64_bis)
    gen2, disc2, _, _ = trainer.build_model_opt()
    check.is_true(torch.allclose(gen.state_dict()['conv1.0.module.bias'],
                                 gen2.state_dict()['conv1.0.module.bias']))
    check.is_true(torch.allclose(disc.state_dict()['conv1.0.module.bias'],
                                 disc2.state_dict()['conv1.0.module.bias']))
    shutil.rmtree('res/tmp_test/models/')


def test_generate_data(mocker: MockerFixture,
                       configs: Tuple[GlobalConfig, GlobalConfig]) -> None:
    """Test generate_data."""
    _, config64 = configs
    data_loader = mocker.MagicMock(n_classes=4)
    trainer = UncondTrainerSAGAN(data_loader=data_loader, config=config64)
    gen = UncondSAGenerator(4, config64.model).to("cuda:0")
    data, attentions = trainer.generate_data(gen)
    check.is_instance(data, np.ndarray)
    check.equal(data.shape, (2, 64, 64, 3))
    check.is_instance(attentions, list)
    check.equal(len(attentions), 1)
