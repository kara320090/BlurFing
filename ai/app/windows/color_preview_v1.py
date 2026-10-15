"""Bounded display-only ICC conversion; saved files/returned arrays are untouched."""
import io
from PIL import ImageCms,ImageOps

MAX_PREVIEW=(900,550)


def display_preview(image):
    preview=ImageOps.exif_transpose(image)
    preview.thumbnail(MAX_PREVIEW)
    icc=preview.info.get('icc_profile')
    if icc is None:return preview
    try:
        if preview.mode not in ('RGB','RGBA'):raise ValueError('preview_ICC_mode_not_supported')
        profile=ImageCms.ImageCmsProfile(io.BytesIO(icc))
        if profile.profile.xcolor_space.strip()!='RGB':raise ValueError('preview_RGB_ICC_required')
        # Perform color conversion after orientation+thumbnail. LittleCMS never
        # receives the full-resolution raster and does not alter final PNG data.
        converted=ImageCms.profileToProfile(preview,profile,ImageCms.createProfile('sRGB'),
            renderingIntent=1,outputMode=preview.mode,inPlace=False)
    except Exception as error:
        preview.close();raise ValueError('display_preview_RGB_ICC_not_supported') from error
    preview.close();return converted
