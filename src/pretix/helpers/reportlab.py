from PIL.Image import BICUBIC
from reportlab.lib.utils import ImageReader


class ThumbnailingImageReader(ImageReader):
    def resize(self, width, height, dpi):
        if width is None:
            width = height * self._image.size[0] / self._image.size[1]
        if height is None:
            height = width * self._image.size[1] / self._image.size[0]
        self._image.thumbnail(
            size=(int(width * dpi / 72), int(height * dpi / 72)),
            resample=BICUBIC
        )
        self._data = None
        return width, height

    def _jpeg_fh(self):
        # Bypass a reportlab-internal optimization that falls back to the original
        # file handle if the file is a JPEG, and therefore does not respect the
        # (smaller) size of the modified image.
        return None
