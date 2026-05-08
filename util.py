import json
from conf import pubapi


def jstr(v):
    return json.dumps(v, ensure_ascii=False)


def toint(v, d=0):
    try:
        return int(v)
    except Exception:
        return d


def _abs_api(path):
    p = (path or '').strip()
    if not p:
        return ''
    if p.startswith('http://') or p.startswith('https://'):
        return p
    if not p.startswith('/'):
        p = f'/{p}'
    if p.startswith('/api/'):
        p = p[4:]
    return f'{pubapi}{p}'


def avurl(raw):
    val = (raw or '').strip()
    if not val:
        return ''
    if val.startswith('/api/avatar/'):
        return _abs_api(val)
    if val.startswith('/avatar/'):
        return _abs_api(val)
    if val.startswith('api/avatar/'):
        return _abs_api(val)
    if val.startswith('avatar/'):
        return _abs_api(val)
    return val


def fext(name):
    if not name or '.' not in name:
        return ''
    return name.rsplit('.', 1)[-1].strip().lower()


def murl(txt):
    raw = (txt or '').strip()
    if ':' not in raw:
        return '', ''
    pfx, val = raw.split(':', 1)
    pfx = pfx.strip().lower()
    val = val.strip()
    if pfx not in {'file', 'voice'}:
        return '', ''
    return pfx, val


def dlurl(url):
    if not url:
        return ''
    if 'cloud.onlysq.ru/file/' not in url:
        return url
    if 'mode=dl' in url:
        return url
    sep = '&' if '?' in url else '?'
    return f'{url}{sep}mode=dl'
