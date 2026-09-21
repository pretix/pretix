def get_session_key_for_api_auth(user, auth):
    if user.is_authenticated:
        return f'api-upload-User-{user.pk}'
    else:
        return f'api-upload-{str(type(auth))}-{auth.pk}'


def get_session_key_for_api_request(request):
    return get_session_key_for_api_auth(request.user, request.auth)
