# Code adapted from https://github.com/heykeetae/Self-Attention-GAN

"""Modules for SAGAN model."""

from typing import List, Optional, Tuple

import numpy as np
import torch
from einops import rearrange
from torch import nn

from utils.configs import ConfigType
from utils.data.process import color_data_np
from utils.sagan.spectral import SpectralNorm

TensorWithAttn = Tuple[torch.Tensor, List[torch.Tensor]]


class SelfAttention(nn.Module):
    """Self attention Layer.

    Parameters
    ----------
    in_dim : int
        Input feature map dimension (channels).
    att_dim : int, optional
        Attention map dimension for each query and key
        (and value if full_values is False).
        By default, in_dim // 8.
    full_values : bool, optional
        Whether to have value dimension equal to full dimension
        (in_dim) or reduced to in_dim // 2. In the latter case,
        the output of the attention is projected to full dimension
        by an additional 1*1 convolution. By default, True.
    """

    def __init__(self, in_dim: int, att_dim: Optional[int] = None,
                 full_values: bool = True) -> None:
        super().__init__()
        self.chanel_in = in_dim
        # By default, query and key dimensions are input dim / 8.
        att_dim = in_dim // 8 if att_dim is None else att_dim

        self.query_conv = nn.Conv2d(in_channels=in_dim, out_channels=att_dim,
                                    kernel_size=1)
        self.key_conv = nn.Conv2d(in_channels=in_dim, out_channels=att_dim,
                                  kernel_size=1)
        if full_values:
            self.value_conv = nn.Conv2d(in_channels=in_dim,
                                        out_channels=in_dim,
                                        kernel_size=1)
            self.out_conv = None
        else:
            self.value_conv = nn.Conv2d(in_channels=in_dim,
                                        out_channels=in_dim // 2,
                                        kernel_size=1)
            self.out_conv = nn.Conv2d(in_channels=in_dim // 2,
                                      out_channels=in_dim,
                                      kernel_size=1)
        # gamma: learned scale factor for residual connection
        self.gamma = nn.Parameter(torch.zeros(1))

    def forward(self, x: torch.Tensor) -> TensorWithAttn:
        """Forward pass.

        Parameters
        ----------
        x : torch.Tensor
            Input feature maps of shape (B, C, W, H).

        Returns
        -------
        out : torch.Tensor
            Self attention maps + input feature maps.
        attention : torch.Tensor
            Attention maps of shape (B, W*H~queries, W*H~keys)
        """
        _, _, width, height = x.size()
        queries = self.query_conv(x)
        keys = self.key_conv(x)
        values = self.value_conv(x)

        queries = rearrange(queries, 'B Cqk Wq Hq -> B (Wq Hq) Cqk')
        keys = rearrange(keys, 'B Cqk Wk Hk -> B Cqk (Wk Hk)')
        unnorm_attention = torch.bmm(queries, keys)  # (B, WH~query, WH~key)
        attention = nn.Softmax(dim=-1)(unnorm_attention)
        attention_t = rearrange(attention, 'B WHq WHk -> B WHk WHq')

        values = rearrange(values, 'B Cv Wv Hv -> B Cv (Wv Hv)')
        out = torch.bmm(values, attention_t)  # (B, Cv, WH)
        out = rearrange(out, 'B Cv (W H) -> B Cv W H', W=width, H=height)

        if self.out_conv is not None:
            out = self.out_conv(out)

        out = self.gamma * out + x

        return out, attention


class SADiscriminator(nn.Module):
    """Self-attention discriminator."""

    def __init__(self, n_classes: int, model_config: ConfigType) -> None:
        super().__init__()
        self.n_classes = n_classes
        self.data_size = model_config.data_size

        datasize_to_num_blocks = {32: 4, 64: 5, 128: 6, 256: 7}
        num_blocks = datasize_to_num_blocks[model_config.data_size]
        self.num_blocks = num_blocks
        # make_attention[i] is True if adding self-attention
        # to {i+1}-th block output
        make_attention = [i + 1 in model_config.attn_layer_num
                          for i in range(num_blocks)]
        self.make_attention = make_attention

        attn_id = 1  # Attention layers id
        for i in range(1, num_blocks):
            if i == 1:  # First block:
                block = self._make_disc_block(n_classes,
                                              model_config.d_conv_dim,
                                              kernel_size=4, stride=2,
                                              padding=1)
                current_dim = model_config.d_conv_dim
            else:
                block = self._make_disc_block(current_dim,
                                              current_dim * 2,
                                              kernel_size=4, stride=2,
                                              padding=1)
                current_dim = current_dim * 2
            # Add conv block to the model
            setattr(self, f'conv{i}', block)
            if make_attention[i - 1]:
                attn = SelfAttention(current_dim,
                                     full_values=model_config.full_values)
                # Add self-attention to the model
                setattr(self, f'attn{attn_id}', attn)
                attn_id += 1

        self.conv_last = nn.Sequential(
            nn.Conv2d(current_dim, 1, kernel_size=4),)

        self.init_weights(model_config.init_method)

    def init_weights(self, init_method: str) -> None:
        """Initialize weights."""
        if init_method == 'default':
            return
        for _, param in self.named_parameters():
            if param.ndim == 4:
                if init_method == 'orthogonal':
                    nn.init.orthogonal_(param)
                elif init_method == 'glorot':
                    nn.init.xavier_uniform_(param)
                elif init_method == 'normal':
                    nn.init.normal_(param, 0, 0.02)
                else:
                    raise ValueError(
                        f'Unknown init method: {init_method}. Should be one '
                        'of "default", "orthogonal", "glorot", "normal".')

    def _make_disc_block(self, in_channels: int, out_channels: int,
                         kernel_size: int, stride: int,
                         padding: int) -> nn.Module:
        """Return a self-attention discriminator block."""
        layers = []
        layers.append(
            SpectralNorm(
                nn.Conv2d(in_channels, out_channels, kernel_size=kernel_size,
                          stride=stride, padding=padding)))
        layers.append(nn.LeakyReLU(0.1))
        module = nn.Sequential(*layers)
        return module

    def forward(self, x: torch.Tensor) -> TensorWithAttn:
        """Forward pass.

        Parameters
        ----------
        x : torch.Tensor
            Input data of shape (B, num_classes, data_size, data_size).

        Returns
        -------
        x : torch.Tensor
            Prediction of discriminator over batch, of shape (B,).
        att_list : list[torch.Tensor]
            Attention maps from all dot product attentions
            of shape (B, W*H~queries, W*H~keys).
        """
        att_list: List[torch.Tensor] = []
        for i in range(1, self.num_blocks):
            x = getattr(self, f'conv{i}')(x)
            if self.make_attention[i - 1]:
                x, att = getattr(self, f'attn{len(att_list) + 1}')(x)
                att_list.append(att)

        x = self.conv_last(x).squeeze()

        if x.ndim == 0:  # when batch size is 1
            x = x.unsqueeze(0)

        return x, att_list


class SAGenerator(nn.Module):
    """Self-attention generator."""

    def __init__(self, n_classes: int, model_config: ConfigType) -> None:
        super().__init__()
        self.n_classes = n_classes
        self.data_size = model_config.data_size

        datasize_to_num_blocks = {32: 4, 64: 5, 128: 6, 256: 7}
        num_blocks = datasize_to_num_blocks[model_config.data_size]
        self.num_blocks = num_blocks
        # make_attention[i] is True if adding self-attention
        # to {i+1}-th block output
        make_attention = [i + 1 in model_config.attn_layer_num
                          for i in range(num_blocks)]
        self.make_attention = make_attention

        repeat_num = int(np.log2(self.data_size)) - 3
        mult = 2**repeat_num  # 4 if data_size=32, 8 if data_size=64, ...

        attn_id = 1  # Attention layers id
        for i in range(1, num_blocks):
            if i == 1:  # First block:
                block = self._make_gen_block(model_config.z_dim,
                                             model_config.g_conv_dim * mult,
                                             kernel_size=4, stride=1,
                                             padding=0)
                current_dim = model_config.g_conv_dim * mult
            else:
                block = self._make_gen_block(current_dim,
                                             current_dim // 2,
                                             kernel_size=4, stride=2,
                                             padding=1)
                current_dim = current_dim // 2
            # Add conv block to the model
            setattr(self, f'conv{i}', block)
            if make_attention[i - 1]:
                attn = SelfAttention(current_dim,
                                     full_values=model_config.full_values)
                # Add self-attention to the model
                setattr(self, f'attn{attn_id}', attn)
                attn_id += 1

        self.conv_last = nn.Sequential(
            nn.ConvTranspose2d(current_dim, n_classes, kernel_size=4, stride=2,
                               padding=1))

        self.init_weights(model_config.init_method)

    def init_weights(self, init_method: str) -> None:
        """Initialize weights."""
        if init_method == 'default':
            return
        for _, param in self.named_parameters():
            if param.ndim == 4:
                if init_method == 'orthogonal':
                    nn.init.orthogonal_(param)
                elif init_method == 'glorot':
                    nn.init.xavier_uniform_(param)
                elif init_method == 'normal':
                    nn.init.normal_(param, 0, 0.02)
                else:
                    raise ValueError(
                        f'Unknown init method: {init_method}. Should be one '
                        'of "default", "orthogonal", "glorot", "normal".')

    def _make_gen_block(self, in_channels: int, out_channels: int,
                        kernel_size: int, stride: int,
                        padding: int) -> nn.Module:
        """Return a self-attention generator block."""
        layers = []
        layers.append(
            SpectralNorm(
                nn.ConvTranspose2d(in_channels, out_channels,
                                   kernel_size=kernel_size, stride=stride,
                                   padding=padding)))
        layers.append(nn.BatchNorm2d(out_channels))
        layers.append(nn.ReLU())
        return nn.Sequential(*layers)

    def forward(self, z: torch.Tensor) -> TensorWithAttn:
        """Forward pass.

        Parameters
        ----------
        z : torch.Tensor
            Random input of shape (B, z_dim)

        Returns
        -------
        x : torch.Tensor
            Generated data of shape (B, 3, data_size, data_size).
        att_list : list[torch.Tensor]
            Attention maps from all dot product attentions
            of shape (B, W*H~queries, W*H~keys).
        """
        att_list: List[torch.Tensor] = []
        x = rearrange(z, 'B z_dim -> B z_dim 1 1')
        for i in range(1, self.num_blocks):
            x = getattr(self, f'conv{i}')(x)
            if self.make_attention[i - 1]:
                x, att = getattr(self, f'attn{len(att_list) + 1}')(x)
                att_list.append(att)

        x = self.conv_last(x)
        x = nn.Softmax(dim=1)(x)
        return x, att_list

    def generate(self, z_input: torch.Tensor,
                 with_attn: bool = False) -> Tuple[np.ndarray,
                                                   List[torch.Tensor]]:
        """Return generated images and eventually attention list."""
        out, attn_list = self.forward(z_input)
        # Quantize + color generated data
        out = torch.argmax(out, dim=1)
        out = out.detach().cpu().numpy()
        images = color_data_np(out)
        if with_attn:
            return images, attn_list
        return images, []
