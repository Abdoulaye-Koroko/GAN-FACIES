"""Utilities for evaluation."""
import random
from typing import List, Union

import numpy as np
import torch
from PIL import Image

from utils.data.process import color_data_np, to_img_grid


def generate_pixel_maps(batch_size: int, n_classes: int,
                        n_pixels: Union[int, List[int]],
                        data_size: int,
                        device: torch.device = "cpu") -> np.ndarray:
    """Generate pixel maps and eventually color them.

    Parameters
    ----------
    batch_size : int
        Number of images to generate.
    n_classes : int
        Number of classes.
    n_pixels : int or List[int] (length 2)
        If int, the number of pixels to sample for each 2D matrix.
        If tuple, the number of pixels to sample for each 2D matrix
        will be sampled uniformly between the two values.
    data_size : int
        Size of the data.
    device : torch.device, optional
        Device to use. By default "cpu".

    Returns
    -------
    pixel_maps : torch.Tensor
        Pixel maps of size (B, n_classes, H, W) (dtype torch.float32).
    """
    if isinstance(n_pixels, int):
        n_pixels_int = n_pixels
    elif isinstance(n_pixels, list) and len(n_pixels) == 2:
        n_pixels_int = np.random.randint(n_pixels[0], n_pixels[1])
    else:
        if isinstance(n_pixels, list):
            raise ValueError("n_pixels must be int or list of length 2, "
                             f"found list of lenght {len(n_pixels)}.")
        raise ValueError("n_pixels must be int or tuple of 2 ints, "
                         f"found type {type(n_pixels)}.")
    pixel_maps = torch.zeros((batch_size, n_classes, data_size, data_size),
                             device=device, dtype=torch.float32)
    for i_batch in range(batch_size):
        tuples = [(i, j) for i in range(data_size) for j in range(data_size)]
        pixels_idx = random.sample(tuples, n_pixels_int)  # without replacement
        pixels_h = [i for i, _ in pixels_idx]
        pixels_w = [j for _, j in pixels_idx]
        classes = torch.randint(0, n_classes, (n_pixels_int, ), device=device)
        pixel_maps[i_batch, classes, pixels_h, pixels_w] = 1.0
        # Class 0 here is actually the mask of the pixels to keep
        pixel_maps[i_batch, 0, pixels_h, pixels_w] = 1.0
    return pixel_maps


def colorize_pixel_map(pixel_maps: torch.Tensor) -> Image:
    """Colorize pixel maps using PIL under grid format."""
    pixel_maps_np = pixel_maps.detach().cpu().numpy()
    pixel_maps_np = np.transpose(pixel_maps_np, (0, 2, 3, 1))
    mask_pixels = pixel_maps_np[..., 0].copy()
    mask_pixels = mask_pixels.astype(np.uint8)

    pixel_maps_np[..., 0] = np.all(pixel_maps_np[..., 1:] == 0,
                                   axis=-1).astype(np.float32)
    pixel_maps_np = np.argmax(pixel_maps_np, axis=-1)
    colored_pixel_maps = color_data_np(pixel_maps_np)
    colored_pixel_maps *= mask_pixels[..., None]

    colored_pixel_maps = to_img_grid(colored_pixel_maps)
    colored_pixel_maps = Image.fromarray(colored_pixel_maps)
    return colored_pixel_maps
