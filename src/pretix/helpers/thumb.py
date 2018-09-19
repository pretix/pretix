import hashlib
from io import BytesIO

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from PIL import Image
from PIL.Image import LANCZOS

from pretix.helpers.models import Thumbnail


class ThumbnailError(Exception):
    pass


def get_sizes(size, imgsize):
    crop = False
    if size.endswith('^'):
        crop = True
        size = size[:-1]

    if 'x' in size:
        size = [int(p) for p in size.split('x')]
    else:
        size = [int(size), int(size)]

    if crop:
        wfactor = min(1, size[0] / imgsize[0])
        hfactor = min(1, size[1] / imgsize[1])
        if wfactor == hfactor:
            return (int(imgsize[0] * wfactor), int(imgsize[1] * hfactor)), \
                   (0, int((imgsize[1] * wfactor - imgsize[1] * hfactor) / 2),
                    imgsize[0] * hfactor, int((imgsize[1] * wfactor + imgsize[1] * wfactor) / 2))
        elif wfactor > hfactor:
            return (int(size[0]), int(imgsize[1] * hfactor)), \
                   (0, int((imgsize[1] * wfactor - size[1]) / 2), size[0], int((imgsize[1] * wfactor + size[1]) / 2))
        else:
            return (int(imgsize[0] * hfactor), int(size[1])), \
                   (int((imgsize[0] * hfactor - size[0]) / 2), 0, int((imgsize[0] * hfactor + size[0]) / 2), size[1])
    else:
        wfactor = min(1, size[0] / imgsize[0])
        hfactor = min(1, size[1] / imgsize[1])
        if wfactor == hfactor:
            return (int(imgsize[0] * hfactor), int(imgsize[1] * wfactor)), None
        elif wfactor < hfactor:
            return (size[0], int(imgsize[1] * wfactor)), None
        else:
            return (int(imgsize[0] * hfactor), size[1]), None


def create_thumbnail(sourcename, size):
    source = default_storage.open(sourcename)
    image = Image.open(BytesIO(source.read()))
    try:
        image.load()
    except:
        raise ThumbnailError('Could not load image')

    scale, crop = get_sizes(size, image.size)
    image = image.resize(scale, resample=LANCZOS)
    if crop:
        image = image.crop(crop)

    checksum = hashlib.md5(image.tobytes()).hexdigest()
    name = checksum + '.' + size.replace('^', 'c') + '.png'
    buffer = BytesIO()
    if image.mode not in ("1", "L", "RGB", "RGBA"):
        image = image.convert('RGB')
    image.save(fp=buffer, format='PNG')
    imgfile = ContentFile(buffer.getvalue())

    t = Thumbnail.objects.create(source=sourcename, size=size)
    t.thumb.save(name, imgfile)
    return t


def get_thumbnail(source, size):
    # Assumes files are immutable
    try:
        return Thumbnail.objects.get(source=source, size=size)
    except Thumbnail.DoesNotExist:
        return create_thumbnail(source, size)
