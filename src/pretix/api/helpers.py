from pretix.base.models import (
    CachedFile
)
from rest_framework.exceptions import ValidationError
from django.core.exceptions import ValidationError as DjangoValidationError
from django.conf import settings

def handle_file_upload(data, user, auth, allowed_types):
    try:
        cf = CachedFile.objects.get(
            session_key=f'api-upload-{str(type(user or auth))}-{(user or auth).pk}',
            file__isnull=False,
            pk=data[len("file:"):],
        )
    except (ValidationError, DjangoValidationError, IndexError):  # invalid uuid
        raise ValidationError('The submitted file ID "{fid}" was not found.'.format(fid=data))
    except CachedFile.DoesNotExist:
        raise ValidationError('The submitted file ID "{fid}" was not found.'.format(fid=data))

    if cf.type not in allowed_types:
        raise ValidationError('The submitted file "{fid}" has a file type that is not allowed in this field.'.format(fid=data))
    if cf.file.size > settings.FILE_UPLOAD_MAX_SIZE_OTHER:
        raise ValidationError('The submitted file "{fid}" is too large to be used in this field.'.format(fid=data))

    return cf.file