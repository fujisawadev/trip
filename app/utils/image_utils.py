import io
import uuid
from PIL import Image, ImageOps


def process_image_for_upload(file_storage, max_dimension: int = 2000, jpeg_quality: int = 85) -> tuple[io.BytesIO, str, str]:
    """
    アップロード前に画像をリサイズ・圧縮し、JPEGに正規化して返す。

    Returns:
        (buffer, filename_ext, content_type)
    """
    unique_name = f"{uuid.uuid4().hex}.jpg"
    out = io.BytesIO()

    img = Image.open(file_storage)
    try:
        img = ImageOps.exif_transpose(img)
    except Exception:
        pass

    if img.mode in ('RGBA', 'LA'):
        background = Image.new('RGB', img.size, (255, 255, 255))
        background.paste(img, mask=img.split()[-1])
        img = background
    elif img.mode != 'RGB':
        img = img.convert('RGB')

    width, height = img.size
    max_side = max(width, height)
    if max_side > max_dimension:
        scale = max_dimension / float(max_side)
        new_size = (int(width * scale), int(height * scale))
        img = img.resize(new_size, Image.LANCZOS)

    img.save(out, format='JPEG', quality=jpeg_quality, optimize=True, progressive=True)
    out.seek(0)
    return out, unique_name, 'image/jpeg'


