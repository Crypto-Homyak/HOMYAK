import threading

from util import jstr

wslk = threading.Lock()
wsmap = {}


def wsadd(uid, ws):
    with wslk:
        wsmap.setdefault(uid, set()).add(ws)


def wsdel(uid, ws):
    with wslk:
        arr = wsmap.get(uid)
        if not arr:
            return
        arr.discard(ws)
        if not arr:
            wsmap.pop(uid, None)


def wspush(uid, pay):
    with wslk:
        arr = list(wsmap.get(uid, set()))
    if not arr:
        return
    raw = jstr(pay)
    dead = []
    for ws in arr:
        try:
            ws.send(raw)
        except Exception:
            dead.append(ws)
    if dead:
        with wslk:
            cur = wsmap.get(uid, set())
            for ws in dead:
                cur.discard(ws)
            if not cur:
                wsmap.pop(uid, None)
