from pretix.base.models import (
    CachedFile
)
from rest_framework.exceptions import ValidationError
from django.core.exceptions import ValidationError as DjangoValidationError
from django.conf import settings

def handle_file_upload(data, user, auth, allowed_types):
    try:
        cf = CachedFile.objects.get(
            file__isnull=False,
            pk=data[len("file:"):],
        )
        if cf.session_key == "api-upload-<class 'django.contrib.auth.models.AnonymousUser'>-None":
            # OK, backwards-compatibility of a security bug fixed 2026-09, delete this at some point, but should
            # also be harmless because all files with this key are expired one day after deployment of this fix
            # and no new files with this key are created
            pass
        elif cf.session_key != get_session_key_for_api_auth(user, auth):
            raise ValidationError('The submitted file ID "{fid}" was not found.'.format(fid=data))
    except (ValidationError, BaseValidationError, IndexError):  # invalid uuid
        raise ValidationError('The submitted file ID "{fid}" was not found.'.format(fid=data))
    except CachedFile.DoesNotExist:
        raise ValidationError('The submitted file ID "{fid}" was not found.'.format(fid=data))

    if cf.type not in allowed_types:
        raise ValidationError('The submitted file "{fid}" has a file type that is not allowed in this field.'.format(fid=data))
    if cf.file.size > settings.FILE_UPLOAD_MAX_SIZE_OTHER:
        raise ValidationError('The submitted file "{fid}" is too large to be used in this field.'.format(fid=data))

    return cf.file