from functools import lru_cache
from io import BytesIO

from PIL import Image, ImageOps


@lru_cache(maxsize=128)
def thumbnail(repository, asset_id) -> bytes:
    """Display derivative only. Original asset bytes are immutable and retained.

    Bounded process cache plus HTTP caching avoids repeated image decoding.
    No extractor, feature data or original file is modified.
    """
    content = repository.get_asset_bytes(asset_id)
    if content is None:
        raise LookupError('ASSET_NOT_FOUND')
    with Image.open(BytesIO(content)) as original:
        original.thumbnail((480, 480))
        image = ImageOps.exif_transpose(original).convert('RGBA')
        output = BytesIO()
        image.save(output, format='WEBP', quality=75, icc_profile=original.info.get('icc_profile', b''))
        return output.getvalue()
