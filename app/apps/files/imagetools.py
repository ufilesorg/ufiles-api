import itertools
from fractions import Fraction
from io import BytesIO

import numpy as np
from colorthief import MMCQ
from PIL import Image
from sklearn.cluster import KMeans


def rgb_to_hex(rgb):
    """Convert RGB color to HEX."""
    return "#{:02x}{:02x}{:02x}".format(int(rgb[0]), int(rgb[1]), int(rgb[2]))


def rgb_to_xyz(rgb):
    r, g, b = rgb

    # Normalize the RGB values to the range [0, 1]
    r = r / 255.0
    g = g / 255.0
    b = b / 255.0

    # Apply the gamma correction (inverse of sRGB companding)
    if r > 0.04045:
        r = ((r + 0.055) / 1.055) ** 2.4
    else:
        r = r / 12.92

    if g > 0.04045:
        g = ((g + 0.055) / 1.055) ** 2.4
    else:
        g = g / 12.92

    if b > 0.04045:
        b = ((b + 0.055) / 1.055) ** 2.4
    else:
        b = b / 12.92

    # Convert to XYZ using the RGB to XYZ matrix transformation
    x = r * 0.4124564 + g * 0.3575761 + b * 0.1804375
    y = r * 0.2126729 + g * 0.7151522 + b * 0.0721750
    z = r * 0.0193339 + g * 0.1191920 + b * 0.9503041

    return (x, y, z)


def xyz_to_lab(xyz):
    x, y, z = xyz

    # Define the reference white point
    x_ref = 0.95047
    y_ref = 1.00000
    z_ref = 1.08883

    # Normalize the XYZ values by the reference white point
    x = x / x_ref
    y = y / y_ref
    z = z / z_ref

    # Apply the LAB transformation
    def f(t):
        if t > 0.008856:
            return t ** (1 / 3)
        else:
            return (7.787 * t) + (16 / 116)

    l = 116 * f(y) - 16
    a = 500 * (f(x) - f(y))
    b = 200 * (f(y) - f(z))

    return (l, a, b)


def rgb_to_lab(rgb):
    xyz = rgb_to_xyz(rgb)
    lab = xyz_to_lab(xyz)
    return lab


def extract_color_palette(image: Image.Image, color_count=4, quality=1):
    """Build a color palette.  We are using the median cut algorithm to
    cluster similar colors.

    :param color_count: the size of the palette, max number of colors
    :param quality: quality settings, 1 is the highest quality, the bigger
                    the number, the faster the palette generation, but the
                    greater the likelihood that colors will be missed.
    :return list: a list of tuple in the form (r, g, b)
    """
    image = image.convert("RGBA")
    pixels = image.getdata()
    valid_pixels = [(r, g, b) for r, g, b, a in pixels[::quality] if a >= 125]
    # valid_pixels = [(r, g, b) for r, g, b, a in pixels if a >= 125 and r < 250 and g < 250 and b < 250]

    # Send array to quantize function which clusters values using median cut algorithm
    cmap = MMCQ.quantize(valid_pixels, color_count)
    colors = sorted(
        [
            (cmap.vboxes.contents[i].get("vbox").count, color, rgb_to_hex(*color))
            for i, color in enumerate(cmap.palette)
        ]
    )
    return [color[1] for color in colors]


def old_color_palette(image_bytes, n_colors=2, **kwargs) -> list[str]:
    image = Image.open(image_bytes).convert("RGB")
    np.array(image)
    pixels = np.array(image).reshape(-1, 3)

    kmeans = KMeans(n_clusters=n_colors)
    kmeans.fit(pixels)

    dominant_colors = np.array(kmeans.cluster_centers_, dtype="uint8")

    return dominant_colors


def color_palette(image_bytes, n_colors=2, **kwargs):
    colors = extract_color_palette(image_bytes, n_colors, **kwargs)
    complement_colors = []
    for color in colors:
        lab = rgb_to_lab(color)
        if lab[0] > 50:
            complement_colors.append(rgb_to_hex((0, 0, 0)))
        else:
            complement_colors.append(rgb_to_hex((255, 255, 255)))

    results = [rgb_to_hex(color) for color in colors] + complement_colors
    return results


def add_watermark_to_image(
    background_image_path: str | bytes | Image.Image,
    watermark_image_path: str,
    position: tuple[int, int] = (0, 0),
    resize: tuple[int, int] = None,
) -> Image:
    """
    Add an watermark image to a background image at a specified position using PIL.

    :param background_image_path: Path to the background image.
    :param watermark_image_path: Path to the watermark image.
    :param position: A tuple (x, y) representing the position to place the watermark.
    :param resize: A tuple (w, h) representing the target size of placed watermark.
    :return: An Image object with the watermark added.
    """

    background = Image.open(background_image_path)
    w, h = background.size
    watermark = Image.open(watermark_image_path)

    position = (w + position[0]) % w, (h + position[1]) % h

    if resize:
        watermark = watermark.resize((50, 50))

    background.paste(watermark, position[0], position[1], watermark)

    return background


def get_aspect_ratio_str(width: int, height: int) -> str:
    fr = Fraction(height, width)
    return f"{fr.denominator}:{fr.numerator}"


def resize_image(image: Image.Image, new_width=384, new_height=None) -> Image.Image:
    if new_width is None and new_height is None:
        return image

    original_width, original_height = image.size
    aspect_ratio = original_height / original_width

    if new_height is None:
        new_height = int(aspect_ratio * new_width)
    elif new_width is None:
        new_width = int(new_height / aspect_ratio)

    resized_image = image.resize((new_width, new_height))
    return resized_image


def crop_image(image: Image.Image, sections=(2, 2), **kwargs) -> list[Image.Image]:
    parts = []
    for i, j in itertools.product(range(sections[0]), range(sections[1])):
        x = j * image.width // sections[0]
        y = i * image.height // sections[1]
        region = image.crop(
            (x, y, x + image.width // sections[0], y + image.height // sections[1])
        )
        parts.append(region)
    return parts


def convert_to_webp_bytes(image: Image.Image, quality=None) -> bytes:
    image_bytes = BytesIO()
    image.convert("RGB").save(
        image_bytes,
        format="WebP",
        **{"quality": quality} if quality else {},
    )
    image_bytes.seek(0)
    return image_bytes


def convert_to_webp(image: Image.Image, quality=None) -> Image.Image:
    return Image.open(convert_to_webp_bytes(image, quality=quality))
