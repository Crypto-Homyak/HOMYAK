from flask import request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from conf import akey
from util import toint

salt = 'auth-token-v1'
ser = URLSafeTimedSerializer(akey, salt=salt)


def tokmk(user):
    return ser.dumps({'uid': user.id, 'u': user.username})


def tokok(tok, age):
    try:
        if not tok:
            return None
        return ser.loads(tok, max_age=toint(age))
    except (BadSignature, SignatureExpired):
        return None


def tokbr():
    hdr = (request.headers.get('Authorization') or '').strip()
    if not hdr:
        return ''
    if hdr.lower().startswith('bearer '):
        return hdr[7:].strip()
    return ''


def requid(age):
    dat = tokok(tokbr(), age)
    if not dat:
        return 0
    uid = toint(dat.get('uid'))
    if uid <= 0:
        return 0
    return uid
