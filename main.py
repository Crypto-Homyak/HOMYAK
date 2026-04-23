import datetime as dt
import json
import os
import threading
import uuid

from flask import Flask, jsonify, request, send_from_directory
from flask_sock import Sock
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy import func, or_
from sqlalchemy.orm import aliased

from data import db_session
from data.chat_members import ChatMember
from data.chats import Chat
from data.messages import Message
from data.users import User

app = Flask(
    __name__,
    static_folder='./templates/dist',
    template_folder='./templates/dist',
    static_url_path=''
)
app.config['SECRET_KEY'] = 'yandexlyceum_secret_key'
app.config.setdefault('AUTH_TOKEN_MAX_AGE_SEC', 60 * 60 * 24 * 14)  # 14 days


@app.after_request
def cors(r):
    r.headers['Access-Control-Allow-Origin'] = '*'
    r.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
    r.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, PATCH, DELETE, OPTIONS'
    return r


sk = Sock(app)

ws_lock = threading.Lock()
active_connections_by_user_id: dict[int, set] = {}
AVATAR_EXTS = {'jpg', 'jpeg', 'png', 'webp', 'gif'}
AVATAR_DIR = os.path.join('data', 'avatars')


def _j(v):
    return json.dumps(v, ensure_ascii=False)


def _as_int(v, default=0):
    try:
        return int(v)
    except Exception:
        return default


def vrem_avatar(raw: str | None) -> str:
    val = (raw or '').strip()
    if not val:
        return ''
    if val.startswith('/api/avatar/'):
        return val
    if val.startswith('/avatar/'):
        return f'/api{val}'
    return val


_TOKEN_SALT = 'auth-token-v1'
_token_ser = URLSafeTimedSerializer(app.config['SECRET_KEY'], salt=_TOKEN_SALT)


def itoken(user: User) -> str:
    return _token_ser.dumps({'uid': user.id, 'u': user.username})


def verify_token(token: str) -> dict | None:
    try:
        if not token:
            return None
        return _token_ser.loads(token, max_age=_as_int(app.config.get('AUTH_TOKEN_MAX_AGE_SEC')))
    except (BadSignature, SignatureExpired):
        return None


def _bearer_token() -> str:
    h = (request.headers.get('Authorization') or '').strip()
    if not h:
        return ''
    if h.lower().startswith('bearer '):
        return h[7:].strip()
    return ''


def req_user_id() -> int:
    data = verify_token(_bearer_token())
    if not data:
        return 0
    uid = _as_int(data.get('uid'))
    if uid <= 0:
        return 0
    return uid


def ws_register(user_id: int, ws):
    with ws_lock:
        active_connections_by_user_id.setdefault(user_id, set()).add(ws)


def ws_unreg(user_id: int, ws):
    with ws_lock:
        conns = active_connections_by_user_id.get(user_id)
        if not conns:
            return
        conns.discard(ws)
        if not conns:
            active_connections_by_user_id.pop(user_id, None)


def push_to_user(user_id: int, payload: dict):
    with ws_lock:
        conns = list(active_connections_by_user_id.get(user_id, set()))
    if not conns:
        return
    raw = _j(payload)
    dead = []
    for w in conns:
        try:
            w.send(raw)
        except Exception:
            dead.append(w)
    if dead:
        with ws_lock:
            cur = active_connections_by_user_id.get(user_id, set())
            for w in dead:
                cur.discard(w)
            if not cur:
                active_connections_by_user_id.pop(user_id, None)


def user_out(u: User) -> dict:
    return {
        'id': u.id,
        'username': u.username,
        'name': u.name,
        'email': u.email,
        'avatar': vrem_avatar(u.avatar),
    }


def chat_out(s, chat: Chat, viewer_id: int = 0) -> dict:
    member_rows = (
        s.query(User.id, User.username, User.name, User.avatar)
        .join(ChatMember, ChatMember.uid == User.id)
        .filter(ChatMember.cid == chat.id)
        .order_by(User.id.asc())
        .all()
    )
    members = [{
        'id': r[0],
        'username': r[1],
        'name': r[2],
        'avatar': vrem_avatar(r[3]),
    } for r in member_rows]

    title = chat.title
    if not chat.is_grp and viewer_id > 0:
        other = None
        for m in members:
            if m['id'] != viewer_id:
                other = m
                break
        if other:
            title = (other.get('username') or other.get('name') or title)

    last_msg = (
        s.query(Message.id, Message.cid, Message.uid, Message.txt, Message.cdt)
        .filter(Message.cid == chat.id)
        .order_by(Message.id.desc())
        .first()
    )

    return {
        'id': chat.id,
        'title': title,
        'raw_title': chat.title,
        'is_grp': bool(chat.is_grp),
        'cdt': chat.cdt.isoformat() if chat.cdt else None,
        'members': members,
        'last': None if not last_msg else {
            'id': last_msg[0],
            'cid': last_msg[1],
            'uid': last_msg[2],
            'txt': last_msg[3],
            'ts': (last_msg[4].isoformat() if last_msg[4] else None),
        }
    }


def open_dm(s, me_id: int, other_id: int) -> Chat:
    existing = (
        s.query(Chat)
        .join(ChatMember, ChatMember.cid == Chat.id)
        .filter(Chat.is_grp == False, ChatMember.uid.in_([me_id, other_id]))
        .group_by(Chat.id)
        .having(func.count(ChatMember.id) == 2)
        .having(func.count(func.distinct(ChatMember.uid)) == 2)
        .order_by(Chat.id.desc())
        .first()
    )
    if existing:
        return existing

    a, b = sorted([me_id, other_id])
    chat = Chat(title=f'dm_{a}_{b}', is_grp=False)
    s.add(chat)
    s.flush()
    s.add(ChatMember(uid=me_id, cid=chat.id))
    s.add(ChatMember(uid=other_id, cid=chat.id))
    s.flush()
    return chat


def recent_chats(s, user_id: int, limit: int = 100) -> list[Chat]:
    lim = max(1, min(limit, 200))
    last_msg_subq = (
        s.query(Message.cid.label('cid'), func.max(Message.id).label('last_id'))
        .group_by(Message.cid)
        .subquery()
    )
    return (
        s.query(Chat)
        .join(ChatMember, ChatMember.cid == Chat.id)
        .outerjoin(last_msg_subq, last_msg_subq.c.cid == Chat.id)
        .filter(ChatMember.uid == user_id)
        .order_by(func.coalesce(last_msg_subq.c.last_id, 0).desc(), Chat.id.desc())
        .limit(lim)
        .all()
    )


def _guess_ext(filename: str) -> str:
    if not filename or '.' not in filename:
        return ''
    return filename.rsplit('.', 1)[-1].strip().lower()


@app.route('/')
@app.route('/api')
def index():
    return jsonify({'ok': True, 'service': 'messenger-backend'})


@app.route('/avatar/<path:filename>', methods=['GET'])
@app.route('/api/avatar/<path:filename>', methods=['GET'])
def avatar_file(filename):
    return send_from_directory(AVATAR_DIR, filename)


@app.route('/avatar/upload', methods=['POST'])
@app.route('/api/avatar/upload', methods=['POST'])
def avatar_upload():
    uid = req_user_id()
    if uid <= 0:
        return jsonify({'ok': False, 'err': 'unauthorized'}), 401

    f = request.files.get('avatar')
    if not f or not f.filename:
        return jsonify({'ok': False, 'err': 'avatar file required'}), 400

    ext = _guess_ext(f.filename)
    if ext not in AVATAR_EXTS:
        return jsonify({'ok': False, 'err': 'allowed: jpg,jpeg,png,webp,gif'}), 400

    os.makedirs(AVATAR_DIR, exist_ok=True)
    filename = f'u{uid}_{uuid.uuid4().hex}.{ext}'
    path = os.path.join(AVATAR_DIR, filename)
    f.save(path)
    avatar_url = f'/api/avatar/{filename}'

    s = db_session.get_sess()
    try:
        u = s.get(User, uid)
        if not u:
            return jsonify({'ok': False, 'err': 'user not found'}), 404
        u.avatar = avatar_url
        s.commit()
        out = user_out(u)
    finally:
        s.close()

    push_to_user(uid, {'act': 'user_updated', 'ok': True, 'user': out})

    s = db_session.get_sess()
    try:
        me_cm = aliased(ChatMember)
        peer_cm = aliased(ChatMember)
        peer_ids = (
            s.query(peer_cm.uid)
            .join(me_cm, me_cm.cid == peer_cm.cid)
            .filter(me_cm.uid == uid, peer_cm.uid != uid)
            .distinct()
            .all()
        )
        for row in peer_ids:
            push_to_user(_as_int(row[0]), {'act': 'user_updated', 'ok': True, 'user': out})
    finally:
        s.close()

    return jsonify({'ok': True, 'user': out})


@app.route('/register', methods=['POST'])
@app.route('/api/register', methods=['POST'])
def register():
    d = request.get_json(silent=True) or {}
    username = (d.get('username') or '').strip().lower()
    password = d.get('password') or ''
    name = (d.get('name') or '').strip() or username
    email = (d.get('email') or '').strip().lower() or f'{username}@local'

    if not username or not password:
        return jsonify({'ok': False, 'err': 'username,password required'}), 400

    if len(username) < 3 or len(username) > 32:
        return jsonify({'ok': False, 'err': 'username len 3..32'}), 400
    if any(ch.isspace() for ch in username):
        return jsonify({'ok': False, 'err': 'username without spaces'}), 400

    s = db_session.get_sess()
    try:
        if s.query(User).filter(User.username == username).first():
            return jsonify({'ok': False, 'err': 'username exists'}), 409
        if s.query(User).filter(User.email == email).first():
            return jsonify({'ok': False, 'err': 'email exists'}), 409

        u = User(name=name, username=username, email=email)
        u.set_pw(password)
        s.add(u)
        s.commit()
        token = itoken(u)
        return jsonify({'ok': True, 'user': user_out(u), 'token': token}), 201
    finally:
        s.close()


@app.route('/login', methods=['POST'])
@app.route('/api/login', methods=['POST'])
def login():
    d = request.get_json(silent=True) or {}
    login_value = (d.get('login') or d.get('email') or d.get('username') or '').strip().lower()
    password = d.get('password') or ''

    if not login_value or not password:
        return jsonify({'ok': False, 'err': 'login,password required'}), 400

    s = db_session.get_sess()
    try:
        u = s.query(User).filter(or_(User.email == login_value, User.username == login_value)).first()
        if not u or not u.chk_pw(password):
            return jsonify({'ok': False, 'err': 'bad creds'}), 401
        if not (u.username or '').strip():
            return jsonify({'ok': False, 'err': 'username required'}), 403
        token = itoken(u)
        return jsonify({'ok': True, 'user': user_out(u), 'token': token})
    finally:
        s.close()


@app.route('/me', methods=['GET'])
@app.route('/api/me', methods=['GET'])
def me():
    uid = req_user_id()
    if uid <= 0:
        return jsonify({'ok': False, 'err': 'unauthorized'}), 401
    s = db_session.get_sess()
    try:
        u = s.get(User, uid)
        if not u:
            return jsonify({'ok': False, 'err': 'unauthorized'}), 401
        return jsonify({'ok': True, 'user': user_out(u)})
    finally:
        s.close()


@app.route('/ws-ready', methods=['GET'])
@app.route('/api/ws-ready', methods=['GET'])
def ws_ready():
    return jsonify({
        'ok': True,
        'ws': '/api/ws',
        'acts': [
            'auth',
            'search_users',
            'open_dm',
            'recent_chats',
            'get_chats',
            'get_msgs',
            'send_msg',
        ],
        'err': None
    })



@sk.route('/ws')
@sk.route('/api/ws')
def ws(ws):
    user_id = 0
    ws.send(_j({'act': 'hello', 'ok': True, 'need_auth': True}))
    try:
        while True:
            raw = ws.receive()
            if raw is None:
                break

            try:
                d = json.loads(raw)
            except Exception:
                ws.send(_j({'ok': False, 'err': 'bad json'}))
                continue

            act = (d.get('act') or '').strip().lower()

            if act == 'auth':
                token = (d.get('token') or '').strip()
                data = verify_token(token)
                if not data:
                    ws.send(_j({'act': 'auth', 'ok': False, 'err': 'bad token'}))
                    continue
                uid = _as_int(data.get('uid'))
                if uid <= 0:
                    ws.send(_j({'act': 'auth', 'ok': False, 'err': 'bad token'}))
                    continue
                s = db_session.get_sess()
                try:
                    u = s.get(User, uid)
                    if not u or not (u.username or '').strip():
                        ws.send(_j({'act': 'auth', 'ok': False, 'err': 'user not found'}))
                        continue
                    if user_id and user_id != uid:
                        ws_unreg(user_id, ws)
                    user_id = uid
                    ws_register(user_id, ws)
                    ws.send(_j({'act': 'auth', 'ok': True, 'user': user_out(u)}))
                finally:
                    s.close()
                continue

            if act == 'search_users':
                if user_id <= 0:
                    ws.send(_j({'act': 'search_users', 'ok': False, 'err': 'auth first'}))
                    continue
                q = (d.get('q') or '').strip().lower()
                lim = _as_int(d.get('lim'), 20)
                lim = max(1, min(lim, 50))
                s = db_session.get_sess()
                try:
                    qry = s.query(User).filter(User.username.isnot(None)).filter(User.username != '')
                    if q:
                        qry = qry.filter(User.username.ilike(f'%{q}%'))
                    rows = qry.order_by(User.id.desc()).limit(lim).all()
                    out = [{
                        'id': x.id,
                        'username': x.username,
                        'name': x.name,
                        'avatar': (x.avatar or '').strip(),
                    } for x in rows if x.id != user_id]
                    ws.send(_j({'act': 'search_users', 'ok': True, 'items': out}))
                finally:
                    s.close()
                continue

            if act == 'open_dm':
                if user_id <= 0:
                    ws.send(_j({'act': 'open_dm', 'ok': False, 'err': 'auth first'}))
                    continue
                to_username = (d.get('to') or d.get('username') or '').strip().lower()
                if not to_username:
                    ws.send(_j({'act': 'open_dm', 'ok': False, 'err': 'to required'}))
                    continue
                s = db_session.get_sess()
                try:
                    other = s.query(User).filter(User.username == to_username).first()
                    if not other:
                        ws.send(_j({'act': 'open_dm', 'ok': False, 'err': 'user not found'}))
                        continue
                    if other.id == user_id:
                        ws.send(_j({'act': 'open_dm', 'ok': False, 'err': 'cannot chat with yourself'}))
                        continue
                    chat = open_dm(s, user_id, other.id)
                    s.commit()
                    ws.send(_j({'act': 'open_dm', 'ok': True, 'chat': chat_out(s, chat, user_id)}))
                    push_to_user(other.id, {
                        'act': 'chat_new',
                        'ok': True,
                        'chat': chat_out(s, chat, other.id),
                    })
                finally:
                    s.close()
                continue

            if act == 'get_chats' or act == 'recent_chats':
                if user_id <= 0:
                    ws.send(_j({'act': act, 'ok': False, 'err': 'auth first'}))
                    continue
                lim = _as_int(d.get('lim'), 100)
                s = db_session.get_sess()
                try:
                    chats = recent_chats(s, user_id, lim)
                    items = [chat_out(s, c, user_id) for c in chats]
                    ws.send(_j({'act': act, 'ok': True, 'items': items}))
                finally:
                    s.close()
                continue

            if act == 'get_msgs':
                if user_id <= 0:
                    ws.send(_j({'act': 'get_msgs', 'ok': False, 'err': 'auth first'}))
                    continue
                chat_id = _as_int(d.get('cid'))
                limit = _as_int(d.get('lim'), 50)
                limit = max(1, min(limit, 200))
                if chat_id <= 0:
                    ws.send(_j({'act': 'get_msgs', 'ok': False, 'err': 'cid required'}))
                    continue
                s = db_session.get_sess()
                try:
                    is_member = s.query(ChatMember.id).filter(ChatMember.cid == chat_id, ChatMember.uid == user_id).first()
                    if not is_member:
                        ws.send(_j({'act': 'get_msgs', 'ok': False, 'err': 'forbidden'}))
                        continue
                    msgs = (
                        s.query(Message, User.username, User.name, User.avatar)
                        .join(User, User.id == Message.uid)
                        .filter(Message.cid == chat_id)
                        .order_by(Message.id.desc())
                        .limit(limit)
                        .all()
                    )
                    items = [{
                        'id': m[0].id,
                        'cid': m[0].cid,
                        'uid': m[0].uid,
                        'txt': m[0].txt,
                        'ts': (m[0].cdt.isoformat() if m[0].cdt else None),
                        'username': m[1],
                        'name': m[2],
                        'avatar': (m[3] or '').strip(),
                    } for m in reversed(msgs)]
                    ws.send(_j({'act': 'get_msgs', 'ok': True, 'items': items}))
                finally:
                    s.close()
                continue

            if act == 'send_msg':
                if user_id <= 0:
                    ws.send(_j({'act': 'send_msg', 'ok': False, 'err': 'auth first'}))
                    continue
                cid = _as_int(d.get('cid'))
                txt = (d.get('txt') or '').strip()
                if cid <= 0 or not txt:
                    ws.send(_j({'act': 'send_msg', 'ok': False, 'err': 'cid and txt required'}))
                    continue
                s = db_session.get_sess()
                try:
                    is_member = s.query(ChatMember.id).filter(ChatMember.cid == cid, ChatMember.uid == user_id).first()
                    if not is_member:
                        ws.send(_j({'act': 'send_msg', 'ok': False, 'err': 'forbidden'}))
                        continue

                    msg = Message(uid=user_id, cid=cid, txt=txt)
                    s.add(msg)
                    s.commit()

                    sender = s.get(User, user_id)
                    member_ids = [r[0] for r in s.query(ChatMember.uid).filter(ChatMember.cid == cid).all()]
                    payload = {
                        'act': 'msg',
                        'ok': True,
                        'msg': {
                            'id': msg.id,
                            'cid': msg.cid,
                            'uid': msg.uid,
                            'txt': msg.txt,
                            'ts': (msg.cdt.isoformat() if msg.cdt else None),
                            'username': (sender.username if sender else ''),
                            'name': (sender.name if sender else ''),
                            'avatar': ((sender.avatar or '').strip() if sender else ''),
                        }
                    }
                    chat = s.get(Chat, cid)
                    for mid in member_ids:
                        push_to_user(mid, payload)
                        if chat:
                            push_to_user(mid, {
                                'act': 'chat_recent',
                                'ok': True,
                                'chat': chat_out(s, chat, mid),
                            })
                finally:
                    s.close()
                continue

            ws.send(_j({'ok': False, 'err': 'bad act'}))
    finally:
        if user_id > 0:
            ws_unreg(user_id, ws)


if __name__ == '__main__':
    os.makedirs('db', exist_ok=True)
    os.makedirs(AVATAR_DIR, exist_ok=True)
    db_session.init_db('db/messenger.db')
    app.run(host='0.0.0.0', port=14080, debug=True)
