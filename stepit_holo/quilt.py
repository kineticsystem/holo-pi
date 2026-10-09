"""Reading a quilt's picture, from a file or from the bytes of one."""

import numpy as np
from PIL import Image

# A Portrait's quilt is 11 million pixels, a large one 100 million: still a quilt, not a decompression bomb.
Image.MAX_IMAGE_PIXELS = 300_000_000


def read_quilt(source, name=None):
    """The quilt in `source`, a path or a binary file, as an RGB array. `name` names it in the error."""
    try:
        with Image.open(source) as image:
            return np.asarray(image.convert("RGB"))
    except (OSError, Image.DecompressionBombError) as error:
        raise RuntimeError(f"cannot read the quilt {name or source}: {error}") from error
