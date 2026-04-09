import datetime as dt
import json
import os
import threading

from flask import Flask, jsonify, request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy import func, or_

from data import db_session
from data.chat_members import ChatMember
from data.chats import Chat
from data.messages import Message
from data.users import User
from flask_sock import Sock

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

ws_con = threading.Lock()
active_connections_by_user_id: dict[int, set] = {}

def _j(v):
    return json.dumps(v, ensure_ascii=False)


def _as_int(v, default=0):
    try:
        return int(v)
    except Exception:
        return default


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


def user_from_req():
    data = verify_token(_bearer_token())
    if not data:
        return None
    uid = _as_int(data.get('uid'))
    if uid <= 0:
        return None
    s = db_session.get_sess()
    try:
        return s.get(User, uid)
    finally:
        s.close()


def ws_con(user_id: int, ws):
    with ws_con:
        active_connections_by_user_id.setdefault(user_id, set()).add(ws)


def ws_unreg(user_id: int, ws):
    with ws_con:
        conns = active_connections_by_user_id.get(user_id)
        if not conns:
            return
        conns.discard(ws)
        if not conns:
            active_connections_by_user_id.pop(user_id, None)


def push_to_user(user_id: int, payload: dict):
    with ws_con:
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
        with ws_con:
            cur = active_connections_by_user_id.get(user_id, set())
            for w in dead:
                cur.discard(w)
            if not cur:
                active_connections_by_user_id.pop(user_id, None)


def user_out(u: User) -> dict:
    return {'id': u.id, 'username': u.username, 'name': u.name, 'email': u.email}


def chat_out(s, chat: Chat) -> dict:
    member_rows = (
        s.query(User.id, User.username, User.name)
        .join(ChatMember, ChatMember.uid == User.id)
        .filter(ChatMember.cid == chat.id)
        .order_by(User.id.asc())
        .all()
    )
    last_msg = (
        s.query(Message)
        .filter(Message.cid == chat.id)
        .order_by(Message.id.desc())
        .first()
    )
    return {
        'id': chat.id,
        'title': chat.title,
        'is_grp': bool(chat.is_grp),
        'cdt': chat.cdt.isoformat() if chat.cdt else None,
        'members': [{'id': r[0], 'username': r[1], 'name': r[2]} for r in member_rows],
        'last': None if not last_msg else {
            'id': last_msg.id,
            'cid': last_msg.cid,
            'uid': last_msg.uid,
            'txt': last_msg.txt,
            'ts': (last_msg.cdt.isoformat() if last_msg.cdt else None),
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


@app.route('/')
def index():
    return jsonify({'ok': True, 'service': 'messenger-backend'})


@app.route('/register', methods=['POST'])
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
def me():
    u = user_from_req()
    if not u:
        return jsonify({'ok': False, 'err': 'unauthorized'}), 401
    return jsonify({'ok': True, 'user': user_out(u)})


@app.route('/ws-ready', methods=['GET'])
def ws_ready():
    return jsonify({
        'ok': bool(sk),
        'ws': '/ws',
        'acts': ['bind', 'search_users', 'create_chat', 'get_chats', 'send_msg'],
        'err': None if sk else 'install flask-sock'
    })


if sk:
    @sk.route('/ws')
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
                        ws_con(user_id, ws)
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
                        rows = (
                            qry.order_by(User.id.desc())
                            .limit(lim)
                            .all()
                        )
                        out = [{'id': x.id, 'username': x.username, 'name': x.name} for x in rows if x.id != user_id]
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
                        out = chat_out(s, chat)
                        ws.send(_j({'act': 'open_dm', 'ok': True, 'chat': out}))
                        push_to_user(other.id, {'act': 'chat_new', 'ok': True, 'chat': out})
                    finally:
                        s.close()
                    continue

                if act == 'get_chats':
                    if user_id <= 0:
                        ws.send(_j({'act': 'get_chats', 'ok': False, 'err': 'auth first'}))
                        continue
                    s = db_session.get_sess()
                    try:
                        chats = (
                            s.query(Chat)
                            .join(ChatMember, ChatMember.cid == Chat.id)
                            .filter(ChatMember.uid == user_id)
                            .order_by(Chat.id.desc())
                            .limit(100)
                            .all()
                        )
                        items = [chat_out(s, c) for c in chats]
                        ws.send(_j({'act': 'get_chats', 'ok': True, 'items': items}))
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
                            s.query(Message)
                            .filter(Message.cid == chat_id)
                            .order_by(Message.id.desc())
                            .limit(limit)
                            .all()
                        )
                        items = [{
                            'id': m.id,
                            'cid': m.cid,
                            'uid': m.uid,
                            'txt': m.txt,
                            'ts': (m.cdt.isoformat() if m.cdt else None)
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
                            }
                        }
                        for mid in member_ids:
                            push_to_user(mid, payload)
                    finally:
                        s.close()
                    continue

                ws.send(_j({'ok': False, 'err': 'bad act'}))
        finally:
            if user_id > 0:
                ws_unreg(user_id, ws)


if __name__ == '__main__':
    os.makedirs('db', exist_ok=True)
    db_session.init_db('db/messenger.db')
    app.run(host='0.0.0.0', port=14080, debug=True)
