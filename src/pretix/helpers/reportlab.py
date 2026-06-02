#
# This file is part of pretix (Community Edition).
#
# Copyright (C) 2014-2020  Raphael Michel and contributors
# Copyright (C) 2020-today pretix GmbH and contributors
#
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU Affero General
# Public License as published by the Free Software Foundation in version 3 of the License.
#
# ADDITIONAL TERMS APPLY: Pursuant to Section 7 of the GNU Affero General Public License, additional terms are
# applicable granting you additional permissions and placing additional restrictions on your usage of this software.
# Please refer to the pretix LICENSE file to obtain the full terms applicable to this work. If you did not receive
# this file, see <https://pretix.eu/about/en/license>.
#
# This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied
# warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU Affero General Public License for more
# details.
#
# You should have received a copy of the GNU Affero General Public License along with this program.  If not, see
# <https://www.gnu.org/licenses/>.
#
import logging

from arabic_reshaper import ArabicReshaper
from django.conf import settings
from django.utils.functional import SimpleLazyObject
from PIL import Image
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.platypus import Paragraph

from pretix.presale.style import get_fonts

logger = logging.getLogger(__name__)


class ThumbnailingImageReader(ImageReader):
    def resize(self, width, height, dpi):
        if width is None:
            width = height * self._image.size[0] / self._image.size[1]
        if height is None:
            height = width * self._image.size[1] / self._image.size[0]
        self._image.thumbnail(
            size=(int(width * dpi / 72), int(height * dpi / 72)),
            resample=Image.Resampling.BICUBIC
        )
        self._data = None
        return width, height

    def remove_transparency(self, background_color="WHITE"):
        if "A" in self._image.mode:
            new_image = Image.new("RGBA", self._image.size, background_color)
            new_image.paste(self._image, mask=self._image)
            self._image = new_image.convert("RGB")

    def _jpeg_fh(self):
        # Bypass a reportlab-internal optimization that falls back to the original
        # file handle if the file is a JPEG, and therefore does not respect the
        # (smaller) size of the modified image.
        return None

    def _read_image(self, fp):
        return Image.open(fp, formats=settings.PILLOW_FORMATS_IMAGE)


reshaper = SimpleLazyObject(lambda: ArabicReshaper(configuration={
    'delete_harakat': True,
    'support_ligatures': False,
}))


def font_supports_text(text, font_name):
    if not text:
        return True
    font = pdfmetrics.getFont(font_name)
    return all(
        ord(c) in font.face.charToGlyph or not c.isprintable()
        for c in text
    )


def find_font_supporting_text(fonts, text, preferred_font):
    if font_supports_text(text, preferred_font):
        return preferred_font
    for family, styles in fonts.items():
        if font_supports_text(text, family):
            if (preferred_font.endswith("It") or preferred_font.endswith(" I")) and "italic" in styles:
                return family + " I"
            if (preferred_font.endswith("Bd") or preferred_font.endswith(" B")) and "bold" in styles:
                return family + " B"
            return family
    return preferred_font


class FontFallbackParagraph(Paragraph):
    def __init__(self, text, style=None, *args, **kwargs):
        if style is None:
            style = ParagraphStyle(name='paragraphImplicitDefaultStyle')

        supporting_font = find_font_supporting_text(get_fonts(pdf_support_required=True), text, style.fontName)
        if supporting_font != style.fontName:
            logger.debug(f"replacing {style.fontName} with {supporting_font} for {text!r}")
            style = style.clone(name=style.name + '_' + supporting_font, fontName=supporting_font)
        super().__init__(text, style, *args, **kwargs)


def register_ttf_font_if_new(name, path):
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    if name not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont(name, path))
