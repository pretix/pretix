import hashlib

from django.core.signing import BadSignature, TimestampSigner


def get_token(request, answer):
    if not request.session.session_key:
        request.session.create()
    payload = '{}:{}'.format(request.session.session_key, answer.pk)
    signer = TimestampSigner()
    return signer.sign(hashlib.sha1(payload.encode()).hexdigest())


def check_token(request, answer, token):
    payload = hashlib.sha1('{}:{}'.format(request.session.session_key, answer.pk).encode()).hexdigest()
    signer = TimestampSigner()
    try:
        return payload == signer.unsign(token, max_age=3600 * 24)
    except BadSignature:
        return False
