import json
import datetime as dt

from data import db_session
from data.chat_members import ChatMember
from data.chats import Chat
from data.call_logs import CallLog
from data.messages import Message
from data.users import User
from logic import cids, cpack, crole, cwrite, dmget, lstchat, mkchat, mout, uout, cmng
from util import avurl, jstr, toint
from wshub import wsadd, wsdel, wspush, wson, wsuids
from authz import tokok
from conf import ctok
from sqlalchemy.orm import aliased


def bindws(sk, hub):
    def push_presence(uid, online):
        uid = int(uid)
        pay = {'act': 'presence', 'ok': True, 'uid': uid, 'online': bool(online)}
        s = db_session.get_sess()
        try:
            me = aliased(ChatMember)
            pe = aliased(ChatMember)
            pids = (
                s.query(pe.uid)
                .join(me, me.cid == pe.cid)
                .filter(me.uid == uid, pe.uid != uid)
                .distinct()
                .all()
            )
            for row in pids:
                wspush(int(row[0]), pay)
        finally:
            s.close()

    def mk_call_hist(log, vid, peer):
        st = (log.status or 'ringing').strip().lower()
        dr = int(log.duration or 0)
        ts = log.started.isoformat() if log.started else None
        way = 'out' if int(log.caller_id) == int(vid) else 'in'
        return {
            'id': log.id,
            'cid': log.cid,
            'chat': int(log.chat_id),
            'status': st,
            'duration': dr,
            'ts': ts,
            'dir': way,
            'peer': {
                'id': int(peer.id) if peer else 0,
                'username': (peer.username if peer else ''),
                'name': (peer.name if peer else ''),
                'avatar': avurl((peer.avatar if peer else '') or ''),
                'online': (wson(peer.id) if peer else False),
            },
        }

    @sk.route('/ws')
    @sk.route('/api/ws')
    def ws(ws):
        uid = 0
        ws.send(jstr({'act': 'hello', 'ok': True, 'need_auth': True}))
        try:
            while True:
                raw = ws.receive()
                if raw is None:
                    break

                try:
                    dat = json.loads(raw)
                except Exception:
                    ws.send(jstr({'ok': False, 'err': 'bad json'}))
                    continue

                act = (dat.get('act') or '').strip().lower()

                if act == 'auth':
                    tok = (dat.get('token') or '').strip()
                    tdat = tokok(tok, ctok)
                    if not tdat:
                        ws.send(jstr({'act': 'auth', 'ok': False, 'err': 'bad token'}))
                        continue
                    nid = toint(tdat.get('uid'))
                    if nid <= 0:
                        ws.send(jstr({'act': 'auth', 'ok': False, 'err': 'bad token'}))
                        continue
                    s = db_session.get_sess()
                    try:
                        usr = s.get(User, nid)
                        if not usr or not (usr.username or '').strip():
                            ws.send(jstr({'act': 'auth', 'ok': False, 'err': 'user not found'}))
                            continue
                        if uid and uid != nid:
                            wsdel(uid, ws)
                        uid = nid
                        wsadd(uid, ws)
                        ws.send(jstr({'act': 'auth', 'ok': True, 'user': uout(usr)}))
                        ws.send(jstr({'act': 'presence_bulk', 'ok': True, 'uids': wsuids()}))
                        push_presence(uid, True)
                    finally:
                        s.close()
                    continue

                if act == 'search_users':
                    if uid <= 0:
                        ws.send(jstr({'act': 'search_users', 'ok': False, 'err': 'auth first'}))
                        continue
                    q = (dat.get('q') or '').strip().lower()
                    lim = max(1, min(toint(dat.get('lim'), 20), 50))
                    s = db_session.get_sess()
                    try:
                        qry = s.query(User).filter(User.username.isnot(None)).filter(User.username != '')
                        if q:
                            qry = qry.filter(User.username.ilike(f'%{q}%'))
                        rows = qry.order_by(User.id.desc()).limit(lim).all()
                        out = [
                            {
                                'id': x.id,
                                'username': x.username,
                                'name': x.name,
                                'avatar': avurl(x.avatar),
                                'online': wson(x.id),
                            }
                            for x in rows
                            if x.id != uid
                        ]
                        ws.send(jstr({'act': 'search_users', 'ok': True, 'items': out}))
                    finally:
                        s.close()
                    continue

                if act == 'open_dm':
                    if uid <= 0:
                        ws.send(jstr({'act': 'open_dm', 'ok': False, 'err': 'auth first'}))
                        continue
                    tou = (dat.get('to') or dat.get('username') or '').strip().lower()
                    if not tou:
                        ws.send(jstr({'act': 'open_dm', 'ok': False, 'err': 'to required'}))
                        continue
                    s = db_session.get_sess()
                    try:
                        oth = s.query(User).filter(User.username == tou).first()
                        if not oth:
                            ws.send(jstr({'act': 'open_dm', 'ok': False, 'err': 'user not found'}))
                            continue
                        if oth.id == uid:
                            ws.send(jstr({'act': 'open_dm', 'ok': False, 'err': 'cannot chat with yourself'}))
                            continue
                        chat = dmget(s, uid, oth.id)
                        s.commit()
                        ws.send(jstr({'act': 'open_dm', 'ok': True, 'chat': cpack(s, chat, uid)}))
                        wspush(oth.id, {'act': 'chat_new', 'ok': True, 'chat': cpack(s, chat, oth.id)})
                    finally:
                        s.close()
                    continue

                if act == 'create_chat':
                    if uid <= 0:
                        ws.send(jstr({'act': 'create_chat', 'ok': False, 'err': 'auth first'}))
                        continue
                    ttl = (dat.get('title') or '').strip()
                    knd = (dat.get('kind') or '').strip().lower()
                    mems = dat.get('members') or []
                    if not isinstance(mems, list):
                        mems = []

                    s = db_session.get_sess()
                    try:
                        uids = []
                        for it in mems:
                            if isinstance(it, int):
                                if it > 0:
                                    uids.append(it)
                                continue
                            if isinstance(it, str):
                                un = it.strip().lower()
                                if not un:
                                    continue
                                uu = s.query(User).filter(User.username == un).first()
                                if uu:
                                    uids.append(uu.id)
                        try:
                            chat = mkchat(s, uid, ttl, knd, uids)
                        except ValueError as ex:
                            ws.send(jstr({'act': 'create_chat', 'ok': False, 'err': str(ex)}))
                            continue
                        s.commit()
                        ids = cids(s, chat.id)
                        for mid in ids:
                            pay = {'act': 'chat_new', 'ok': True, 'chat': cpack(s, chat, mid)}
                            wspush(mid, pay)
                        ws.send(jstr({'act': 'create_chat', 'ok': True, 'chat': cpack(s, chat, uid)}))
                    finally:
                        s.close()
                    continue

                if act == 'chat_setadm':
                    if uid <= 0:
                        ws.send(jstr({'act': 'chat_setadm', 'ok': False, 'err': 'auth first'}))
                        continue
                    cid = toint(dat.get('cid'))
                    tid = toint(dat.get('uid'))
                    adm = bool(dat.get('adm'))
                    s = db_session.get_sess()
                    try:
                        chat = s.get(Chat, cid)
                        me = crole(s, cid, uid)
                        if not chat or not me:
                            ws.send(jstr({'act': 'chat_setadm', 'ok': False, 'err': 'forbidden'}))
                            continue
                        if not cmng(chat, me, uid):
                            ws.send(jstr({'act': 'chat_setadm', 'ok': False, 'err': 'only creator'}))
                            continue
                        tar = crole(s, cid, tid)
                        if not tar:
                            ws.send(jstr({'act': 'chat_setadm', 'ok': False, 'err': 'member not found'}))
                            continue
                        if tid == uid:
                            ws.send(jstr({'act': 'chat_setadm', 'ok': False, 'err': 'cannot change yourself'}))
                            continue
                        tar.role = 'admin' if adm else 'member'
                        s.commit()
                        ids = cids(s, cid)
                        for mid in ids:
                            wspush(mid, {'act': 'chat_upd', 'ok': True, 'chat': cpack(s, chat, mid)})
                        ws.send(jstr({'act': 'chat_setadm', 'ok': True}))
                    finally:
                        s.close()
                    continue

                if act == 'chat_add':
                    if uid <= 0:
                        ws.send(jstr({'act': 'chat_add', 'ok': False, 'err': 'auth first'}))
                        continue
                    cid = toint(dat.get('cid'))
                    mems = dat.get('members') or []
                    if not isinstance(mems, list):
                        mems = []
                    s = db_session.get_sess()
                    try:
                        chat = s.get(Chat, cid)
                        me = crole(s, cid, uid)
                        if not chat or not me:
                            ws.send(jstr({'act': 'chat_add', 'ok': False, 'err': 'forbidden'}))
                            continue
                        if (chat.kind or 'dm') == 'dm':
                            ws.send(jstr({'act': 'chat_add', 'ok': False, 'err': 'dm immutable'}))
                            continue
                        if int(chat.owner_id or 0) != uid and (me.role or 'member') != 'admin':
                            ws.send(jstr({'act': 'chat_add', 'ok': False, 'err': 'owner/admin only'}))
                            continue

                        add = []
                        for it in mems:
                            xid = 0
                            if isinstance(it, int):
                                xid = it
                            elif isinstance(it, str):
                                un = it.strip().lower()
                                if not un:
                                    continue
                                uu = s.query(User).filter(User.username == un).first()
                                if uu:
                                    xid = uu.id
                            if xid <= 0:
                                continue
                            if xid in add:
                                continue
                            add.append(xid)

                        for xid in add:
                            if not crole(s, cid, xid):
                                s.add(ChatMember(uid=xid, cid=cid, role='member'))
                        s.commit()

                        ids = cids(s, cid)
                        for mid in ids:
                            wspush(mid, {'act': 'chat_upd', 'ok': True, 'chat': cpack(s, chat, mid)})
                        ws.send(jstr({'act': 'chat_add', 'ok': True}))
                    finally:
                        s.close()
                    continue

                if act == 'chat_kick':
                    if uid <= 0:
                        ws.send(jstr({'act': 'chat_kick', 'ok': False, 'err': 'auth first'}))
                        continue
                    cid = toint(dat.get('cid'))
                    tid = toint(dat.get('uid'))
                    s = db_session.get_sess()
                    try:
                        chat = s.get(Chat, cid)
                        me = crole(s, cid, uid)
                        if not chat or not me:
                            ws.send(jstr({'act': 'chat_kick', 'ok': False, 'err': 'forbidden'}))
                            continue
                        if not cmng(chat, me, uid):
                            ws.send(jstr({'act': 'chat_kick', 'ok': False, 'err': 'only creator'}))
                            continue
                        if tid == uid:
                            ws.send(jstr({'act': 'chat_kick', 'ok': False, 'err': 'cannot kick yourself'}))
                            continue
                        tar = crole(s, cid, tid)
                        if not tar:
                            ws.send(jstr({'act': 'chat_kick', 'ok': False, 'err': 'member not found'}))
                            continue
                        s.delete(tar)
                        s.commit()
                        ids = cids(s, cid)
                        for mid in ids:
                            wspush(mid, {'act': 'chat_upd', 'ok': True, 'chat': cpack(s, chat, mid)})
                        wspush(tid, {'act': 'chat_del', 'ok': True, 'cid': cid})
                        ws.send(jstr({'act': 'chat_kick', 'ok': True}))
                    finally:
                        s.close()
                    continue

                if act in {'get_chats', 'recent_chats'}:
                    if uid <= 0:
                        ws.send(jstr({'act': act, 'ok': False, 'err': 'auth first'}))
                        continue
                    lim = toint(dat.get('lim'), 100)
                    s = db_session.get_sess()
                    try:
                        arr = lstchat(s, uid, lim)
                        out = [cpack(s, c, uid) for c in arr]
                        ws.send(jstr({'act': act, 'ok': True, 'items': out}))
                    finally:
                        s.close()
                    continue

                if act == 'get_msgs':
                    if uid <= 0:
                        ws.send(jstr({'act': 'get_msgs', 'ok': False, 'err': 'auth first'}))
                        continue
                    cid = toint(dat.get('cid'))
                    lim = max(1, min(toint(dat.get('lim'), 50), 200))
                    if cid <= 0:
                        ws.send(jstr({'act': 'get_msgs', 'ok': False, 'err': 'cid required'}))
                        continue
                    s = db_session.get_sess()
                    try:
                        mem = crole(s, cid, uid)
                        if not mem:
                            ws.send(jstr({'act': 'get_msgs', 'ok': False, 'err': 'forbidden'}))
                            continue
                        rows = (
                            s.query(Message, User.username, User.name, User.avatar)
                            .join(User, User.id == Message.uid)
                            .filter(Message.cid == cid)
                            .order_by(Message.id.desc())
                            .limit(lim)
                            .all()
                        )
                        out = [mout(r[0], r[1], r[2], r[3]) for r in reversed(rows)]
                        ws.send(jstr({'act': 'get_msgs', 'ok': True, 'items': out}))
                    finally:
                        s.close()
                    continue

                if act == 'chat_delself':
                    if uid <= 0:
                        ws.send(jstr({'act': 'chat_delself', 'ok': False, 'err': 'auth first'}))
                        continue
                    cid = toint(dat.get('cid'))
                    s = db_session.get_sess()
                    try:
                        chat = s.get(Chat, cid)
                        me = crole(s, cid, uid)
                        if not chat or not me:
                            ws.send(jstr({'act': 'chat_delself', 'ok': False, 'err': 'forbidden'}))
                            continue

                        all_ids = cids(s, cid)
                        owner = int(chat.owner_id or 0) == int(uid)
                        knd = (chat.kind or 'dm').strip().lower()

                        if owner and knd in {'group', 'channel'}:
                            s.delete(chat)
                            s.commit()
                            for mid in all_ids:
                                wspush(mid, {'act': 'chat_del', 'ok': True, 'cid': cid})
                            ws.send(jstr({'act': 'chat_delself', 'ok': True, 'cid': cid, 'full': True}))
                            continue

                        s.delete(me)
                        s.commit()
                        left_ids = cids(s, cid)
                        if not left_ids:
                            zchat = s.get(Chat, cid)
                            if zchat:
                                s.delete(zchat)
                                s.commit()
                        else:
                            zchat = s.get(Chat, cid)
                            if zchat:
                                for mid in left_ids:
                                    wspush(mid, {'act': 'chat_upd', 'ok': True, 'chat': cpack(s, zchat, mid)})
                        wspush(uid, {'act': 'chat_del', 'ok': True, 'cid': cid})
                        ws.send(jstr({'act': 'chat_delself', 'ok': True, 'cid': cid, 'full': False}))
                    finally:
                        s.close()
                    continue

                if act == 'call_hist':
                    if uid <= 0:
                        ws.send(jstr({'act': 'call_hist', 'ok': False, 'err': 'auth first'}))
                        continue
                    lim = max(1, min(toint(dat.get('lim'), 50), 200))
                    s = db_session.get_sess()
                    try:
                        rows = (
                            s.query(CallLog)
                            .filter((CallLog.caller_id == uid) | (CallLog.callee_id == uid))
                            .order_by(CallLog.id.desc())
                            .limit(lim)
                            .all()
                        )
                        out = []
                        for x in rows:
                            pid = x.callee_id if int(x.caller_id) == uid else x.caller_id
                            peer = s.get(User, int(pid))
                            out.append(mk_call_hist(x, uid, peer))
                        ws.send(jstr({'act': 'call_hist', 'ok': True, 'items': out}))
                    finally:
                        s.close()
                    continue

                if act == 'send_msg':
                    if uid <= 0:
                        ws.send(jstr({'act': 'send_msg', 'ok': False, 'err': 'auth first'}))
                        continue
                    cid = toint(dat.get('cid'))
                    txt = (dat.get('txt') or '').strip()
                    knd = (dat.get('kind') or '').strip().lower()
                    url = (dat.get('url') or '').strip()
                    fname = (dat.get('fname') or '').strip()
                    if cid <= 0:
                        ws.send(jstr({'act': 'send_msg', 'ok': False, 'err': 'cid required'}))
                        continue
                    if not txt and not url:
                        ws.send(jstr({'act': 'send_msg', 'ok': False, 'err': 'text required'}))
                        continue
                    if knd not in {'text', 'file', 'voice'}:
                        if url:
                            knd = 'file'
                        else:
                            knd = 'text'

                    if knd == 'file' and url:
                        txt = f'file:{url}'
                    if knd == 'voice' and url:
                        txt = f'voice:{url}'
                    if not txt:
                        txt = url

                    s = db_session.get_sess()
                    try:
                        chat = s.get(Chat, cid)
                        mem = crole(s, cid, uid)
                        if not chat or not mem:
                            ws.send(jstr({'act': 'send_msg', 'ok': False, 'err': 'forbidden'}))
                            continue
                        if not cwrite(chat, mem, uid):
                            ws.send(jstr({'act': 'send_msg', 'ok': False, 'err': 'write forbidden'}))
                            continue

                        msg = Message(uid=uid, cid=cid, txt=txt, kind=knd, meta=url, mname=fname[:255])
                        s.add(msg)
                        s.commit()

                        usr = s.get(User, uid)
                        mids = cids(s, cid)
                        one = mout(msg, (usr.username if usr else ''), (usr.name if usr else ''), (usr.avatar if usr else ''))
                        for mid in mids:
                            wspush(mid, {'act': 'msg', 'ok': True, 'msg': one})
                            wspush(mid, {'act': 'chat_recent', 'ok': True, 'chat': cpack(s, chat, mid)})
                        ws.send(jstr({'act': 'send_msg', 'ok': True, 'msg': one}))
                    finally:
                        s.close()
                    continue

                if act == 'call_start':
                    if uid <= 0:
                        ws.send(jstr({'act': 'call_start', 'ok': False, 'err': 'auth first'}))
                        continue
                    cid = toint(dat.get('cid'))
                    tou = (dat.get('to') or '').strip().lower()
                    s = db_session.get_sess()
                    try:
                        chat = None
                        oth = None
                        if cid > 0:
                            chat = s.get(Chat, cid)
                            if not chat or (chat.kind or '') != 'dm':
                                ws.send(jstr({'act': 'call_start', 'ok': False, 'err': 'dm only'}))
                                continue
                            ids = cids(s, cid)
                            if uid not in ids or len(ids) != 2:
                                ws.send(jstr({'act': 'call_start', 'ok': False, 'err': 'forbidden'}))
                                continue
                            oth = ids[0] if ids[1] == uid else ids[1]
                        else:
                            if not tou:
                                ws.send(jstr({'act': 'call_start', 'ok': False, 'err': 'cid or to required'}))
                                continue
                            uo = s.query(User).filter(User.username == tou).first()
                            if not uo:
                                ws.send(jstr({'act': 'call_start', 'ok': False, 'err': 'user not found'}))
                                continue
                            if uo.id == uid:
                                ws.send(jstr({'act': 'call_start', 'ok': False, 'err': 'bad user'}))
                                continue
                            chat = dmget(s, uid, uo.id)
                            s.commit()
                            oth = uo.id

                        cl = hub.make(uid, oth)
                        lg = s.query(CallLog).filter(CallLog.cid == cl.cid).order_by(CallLog.id.desc()).first()
                        if not lg:
                            lg = CallLog(cid=cl.cid, chat_id=chat.id, caller_id=uid, callee_id=oth, status='ringing')
                            s.add(lg)
                            s.commit()
                        me = s.get(User, uid)
                        wspush(uid, {'act': 'call_ring', 'ok': True, 'cid': cl.cid, 'chat': chat.id})
                        wspush(oth, {
                            'act': 'call_in',
                            'ok': True,
                            'cid': cl.cid,
                            'chat': chat.id,
                            'from': {
                                'id': uid,
                                'username': (me.username if me else ''),
                                'name': (me.name if me else ''),
                                'avatar': avurl((me.avatar if me else '') or ''),
                            },
                        })
                        ws.send(jstr({'act': 'call_start', 'ok': True, 'cid': cl.cid, 'chat': chat.id}))
                    finally:
                        s.close()
                    continue

                if act == 'call_acc':
                    if uid <= 0:
                        ws.send(jstr({'act': 'call_acc', 'ok': False, 'err': 'auth first'}))
                        continue
                    cid = (dat.get('cid') or '').strip()
                    if not hub.can(cid, uid):
                        ws.send(jstr({'act': 'call_acc', 'ok': False, 'err': 'bad call'}))
                        continue
                    cl = hub.get(cid)
                    hub.acc(cid)
                    s = db_session.get_sess()
                    try:
                        lg = s.query(CallLog).filter(CallLog.cid == cid).order_by(CallLog.id.desc()).first()
                        if lg:
                            lg.status = 'talk'
                            lg.accepted = dt.datetime.now()
                            s.commit()
                    finally:
                        s.close()
                    wspush(cl.a, {'act': 'call_go', 'ok': True, 'cid': cid})
                    wspush(cl.b, {'act': 'call_go', 'ok': True, 'cid': cid})
                    ws.send(jstr({'act': 'call_acc', 'ok': True, 'cid': cid}))
                    continue

                if act == 'call_rej':
                    if uid <= 0:
                        ws.send(jstr({'act': 'call_rej', 'ok': False, 'err': 'auth first'}))
                        continue
                    cid = (dat.get('cid') or '').strip()
                    if not hub.can(cid, uid):
                        ws.send(jstr({'act': 'call_rej', 'ok': False, 'err': 'bad call'}))
                        continue
                    cl = hub.get(cid)
                    hub.rej(cid)
                    s = db_session.get_sess()
                    try:
                        lg = s.query(CallLog).filter(CallLog.cid == cid).order_by(CallLog.id.desc()).first()
                        if lg:
                            lg.status = 'rejected'
                            lg.ended = dt.datetime.now()
                            lg.duration = 0
                            s.commit()
                    finally:
                        s.close()
                    if cl:
                        wspush(cl.a, {'act': 'call_stop', 'ok': True, 'cid': cid, 'why': 'rejected'})
                        wspush(cl.b, {'act': 'call_stop', 'ok': True, 'cid': cid, 'why': 'rejected'})
                    ws.send(jstr({'act': 'call_rej', 'ok': True, 'cid': cid}))
                    continue

                if act == 'call_end':
                    if uid <= 0:
                        ws.send(jstr({'act': 'call_end', 'ok': False, 'err': 'auth first'}))
                        continue
                    cid = (dat.get('cid') or '').strip()
                    if not hub.can(cid, uid):
                        ws.send(jstr({'act': 'call_end', 'ok': False, 'err': 'bad call'}))
                        continue
                    cl = hub.get(cid)
                    hub.end(cid)
                    s = db_session.get_sess()
                    try:
                        lg = s.query(CallLog).filter(CallLog.cid == cid).order_by(CallLog.id.desc()).first()
                        if lg:
                            now = dt.datetime.now()
                            lg.ended = now
                            if lg.accepted:
                                lg.status = 'ended'
                                lg.duration = int((now - lg.accepted).total_seconds())
                            else:
                                lg.status = 'missed'
                                lg.duration = 0
                            s.commit()
                    finally:
                        s.close()
                    if cl:
                        wspush(cl.a, {'act': 'call_stop', 'ok': True, 'cid': cid, 'why': 'ended'})
                        wspush(cl.b, {'act': 'call_stop', 'ok': True, 'cid': cid, 'why': 'ended'})
                    ws.send(jstr({'act': 'call_end', 'ok': True, 'cid': cid}))
                    continue

                if act == 'call_offer':
                    if uid <= 0:
                        ws.send(jstr({'act': 'call_offer', 'ok': False, 'err': 'auth first'}))
                        continue
                    cid = (dat.get('cid') or '').strip()
                    sdp = (dat.get('sdp') or '').strip()
                    typ = (dat.get('type') or 'offer').strip()
                    if not hub.can(cid, uid):
                        ws.send(jstr({'act': 'call_offer', 'ok': False, 'err': 'bad call'}))
                        continue
                    if not sdp:
                        ws.send(jstr({'act': 'call_offer', 'ok': False, 'err': 'sdp required'}))
                        continue
                    try:
                        ans = hub.offer(cid, uid, sdp, typ)
                    except Exception as ex:
                        ws.send(jstr({'act': 'call_offer', 'ok': False, 'err': str(ex)}))
                        continue
                    ws.send(jstr({'act': 'call_ans', 'ok': True, 'cid': cid, 'sdp': ans['sdp'], 'type': ans['type']}))
                    continue

                if act == 'call_ice':
                    if uid <= 0:
                        ws.send(jstr({'act': 'call_ice', 'ok': False, 'err': 'auth first'}))
                        continue
                    cid = (dat.get('cid') or '').strip()
                    ice = dat.get('ice') or {}
                    if not isinstance(ice, dict):
                        ice = {}
                    if not hub.can(cid, uid):
                        ws.send(jstr({'act': 'call_ice', 'ok': False, 'err': 'bad call'}))
                        continue
                    try:
                        hub.iceadd(cid, uid, ice)
                    except Exception as ex:
                        ws.send(jstr({'act': 'call_ice', 'ok': False, 'err': str(ex)}))
                        continue
                    ws.send(jstr({'act': 'call_ice', 'ok': True}))
                    continue

                ws.send(jstr({'ok': False, 'err': 'bad act'}))
        finally:
            if uid > 0:
                wsdel(uid, ws)
                if not wson(uid):
                    push_presence(uid, False)
