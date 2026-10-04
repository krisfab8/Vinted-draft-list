"""Normalize browser-undecodable photos without making a model request."""
import io
import warnings

from PIL import Image, ImageOps, UnidentifiedImageError
from pillow_heif import register_heif_opener

register_heif_opener()
MAX_BYTES = 20 * 1024 * 1024
MAX_PIXELS = 32_000_000


class PhotoPreparationError(ValueError):
    pass


def normalize(data):
    if not data:
        raise PhotoPreparationError('The photo is empty. Download it fully or select it again.')
    if len(data) > MAX_BYTES:
        raise PhotoPreparationError('The photo is too large. Choose a smaller copy or standard camera resolution.')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as source:
                if source.width * source.height > MAX_PIXELS:
                    raise PhotoPreparationError('The photo resolution is too large. Choose standard camera resolution.')
                if source.format not in {'JPEG', 'PNG', 'WEBP', 'HEIF', 'AVIF'}:
                    raise PhotoPreparationError('This photo format is unsupported. Save a JPG, PNG, WebP or HEIC copy.')
                # JPEG decoders can reduce before allocating the full camera bitmap.
                source.draft('RGB', (2048, 2048))
                image = ImageOps.exif_transpose(source)
                image.thumbnail((2048, 2048), Image.Resampling.LANCZOS)
                if image.mode in ('RGBA', 'LA') or 'transparency' in image.info:
                    rgba = image.convert('RGBA')
                    rgb = Image.new('RGB', rgba.size, 'white')
                    rgb.paste(rgba, mask=rgba.getchannel('A'))
                else:
                    rgb = image.convert('RGB')
                output = io.BytesIO()
                rgb.save(output, 'JPEG', quality=85, exif=b'')
                return output.getvalue()
    except PhotoPreparationError:
        raise
    except (Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise PhotoPreparationError('The photo resolution is too large. Choose standard camera resolution.') from None
    except (UnidentifiedImageError, OSError, ValueError, EOFError):
        raise PhotoPreparationError('This photo could not be opened. Download it fully or replace it with a JPG or a new camera photo.') from None
