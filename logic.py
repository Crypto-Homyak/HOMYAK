from sqlalchemy import func

from data.chat_members import ChatMember
from data.chats import Chat
from data.messages import Message
from data.users import User
from util import avurl, murl


def uout(u):
    return {
        'id': u.id,
        'username': u.username,
        'name': u.name,
        'email': u.email,
        'avatar': avurl(u.avatar),
    }


def mkind(msg):
    knd = (msg.kind or '').strip().lower()
    if knd in {'text', 'file', 'voice'}:
        if knd in {'file', 'voice'}:
            url = (msg.meta or '').strip()
            if not url:
                pfx, url = murl(msg.txt)
                if pfx:
                    knd = pfx
            return knd, url
        return 'text', ''
    pfx, url = murl(msg.txt)
    if pfx:
        return pfx, url
    return 'text', ''


def mout(msg, uname, name, avatar):
    knd, url = mkind(msg)
    return {
        'id': msg.id,
        'cid': msg.cid,
        'uid': msg.uid,
        'txt': msg.txt,
        'kind': knd,
        'url': url,
        'ts': (msg.cdt.isoformat() if msg.cdt else None),
        'username': uname,
        'name': name,
        'avatar': avurl(avatar),
    }


def crole(s, cid, uid):
    return s.query(ChatMember).filter(ChatMember.cid == cid, ChatMember.uid == uid).first()


def cadm(mem):
    if not mem:
        return False
    return (mem.role or '').strip().lower() == 'admin'


def cown(chat, uid):
    return chat and int(chat.owner_id or 0) == int(uid)


def cwrite(chat, mem, uid):
    if not chat or not mem:
        return False
    knd = (chat.kind or '').strip().lower()
    if knd == 'channel':
        return cown(chat, uid) or cadm(mem)
    return True


def cmng(chat, mem, uid):
    if not chat or not mem:
        return False
    return cown(chat, uid)


def cids(s, cid):
    return [r[0] for r in s.query(ChatMember.uid).filter(ChatMember.cid == cid).all()]


def cpack(s, chat, vid=0):
    rows = (
        s.query(User.id, User.username, User.name, User.avatar, ChatMember.role)
        .join(ChatMember, ChatMember.uid == User.id)
        .filter(ChatMember.cid == chat.id)
        .order_by(User.id.asc())
        .all()
    )
    mems = [
        {
            'id': r[0],
            'username': r[1],
            'name': r[2],
            'avatar': avurl(r[3]),
            'role': (r[4] or 'member'),
        }
        for r in rows
    ]

    me = None
    for m in mems:
        if m['id'] == vid:
            me = m
            break

    ttl = chat.title
    if (chat.kind or 'dm') == 'dm' and vid > 0:
        oth = None
        for m in mems:
            if m['id'] != vid:
                oth = m
                break
        if oth:
            ttl = oth.get('username') or oth.get('name') or ttl

    lst = (
        s.query(Message, User.username, User.name, User.avatar)
        .join(User, User.id == Message.uid)
        .filter(Message.cid == chat.id)
        .order_by(Message.id.desc())
        .first()
    )

    return {
        'id': chat.id,
        'title': ttl,
        'raw': chat.title,
        'is_grp': bool(chat.is_grp),
        'kind': (chat.kind or ('group' if chat.is_grp else 'dm')),
        'own': int(chat.owner_id or 0),
        'my_role': (me.get('role') if me else 'member'),
        'can_w': cwrite(chat, me, vid),
        'cdt': chat.cdt.isoformat() if chat.cdt else None,
        'members': mems,
        'last': (mout(lst[0], lst[1], lst[2], lst[3]) if lst else None),
    }


def dmget(s, meid, oid):
    got = (
        s.query(Chat)
        .join(ChatMember, ChatMember.cid == Chat.id)
        .filter(Chat.kind == 'dm', ChatMember.uid.in_([meid, oid]))
        .group_by(Chat.id)
        .having(func.count(ChatMember.id) == 2)
        .having(func.count(func.distinct(ChatMember.uid)) == 2)
        .order_by(Chat.id.desc())
        .first()
    )
    if got:
        return got

    a, b = sorted([meid, oid])
    chat = Chat(title=f'dm_{a}_{b}', is_grp=False, kind='dm', owner_id=meid)
    s.add(chat)
    s.flush()
    s.add(ChatMember(uid=meid, cid=chat.id, role='member'))
    s.add(ChatMember(uid=oid, cid=chat.id, role='member'))
    s.flush()
    return chat


def lstchat(s, uid, lim=100):
    lim = max(1, min(int(lim or 100), 200))
    sub = s.query(Message.cid.label('cid'), func.max(Message.id).label('lid')).group_by(Message.cid).subquery()
    return (
        s.query(Chat)
        .join(ChatMember, ChatMember.cid == Chat.id)
        .outerjoin(sub, sub.c.cid == Chat.id)
        .filter(ChatMember.uid == uid)
        .order_by(func.coalesce(sub.c.lid, 0).desc(), Chat.id.desc())
        .limit(lim)
        .all()
    )


def mkchat(s, uid, title, kind, ids):
    ttl = (title or '').strip()
    if not ttl:
        raise ValueError('title required')
    knd = (kind or '').strip().lower()
    if knd not in {'group', 'channel'}:
        raise ValueError('bad kind')
    uids = set(int(x) for x in ids if int(x) > 0)
    uids.add(int(uid))

    chat = Chat(title=ttl, is_grp=True, kind=knd, owner_id=uid)
    s.add(chat)
    s.flush()

    for mid in sorted(uids):
        rol = 'admin' if mid == uid else 'member'
        s.add(ChatMember(uid=mid, cid=chat.id, role=rol))
    s.flush()
    return chat
