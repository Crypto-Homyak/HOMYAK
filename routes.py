import os
import uuid

from flask import jsonify, request, send_from_directory
from sqlalchemy import or_
from sqlalchemy.orm import aliased

from authz import requid, tokmk
from conf import avdir, avex, ctok
from data import db_session
from data.chat_members import ChatMember
from data.users import User
from logic import uout
from util import fext
from wshub import wspush


def bindrt(app):
    def push_user(uid, out):
        wspush(uid, {'act': 'user_upd', 'ok': True, 'user': out})
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
                wspush(int(row[0]), {'act': 'user_upd', 'ok': True, 'user': out})
        finally:
            s.close()

    def has_front():
        if not app.static_folder:
            return False
        return os.path.isfile(os.path.join(app.static_folder, 'index.html'))

    @app.route('/api')
    def idx():
        return jsonify({'ok': True, 'service': 'messenger-backend'})

    @app.route('/')
    def front():
        if has_front():
            return app.send_static_file('index.html')
        return jsonify({'ok': True, 'service': 'messenger-frontend-missing'})

    @app.route('/avatar/<path:name>', methods=['GET'])
    @app.route('/api/avatar/<path:name>', methods=['GET'])
    def avget(name):
        return send_from_directory(avdir, name)

    @app.route('/sounds/<path:name>', methods=['GET'])
    @app.route('/api/sounds/<path:name>', methods=['GET'])
    def sndget(name):
        return send_from_directory('sounds', name)

    @app.route('/avatar/upload', methods=['POST'])
    @app.route('/api/avatar/upload', methods=['POST'])
    def avup():
        uid = requid(ctok)
        if uid <= 0:
            return jsonify({'ok': False, 'err': 'unauthorized'}), 401

        fil = request.files.get('avatar')
        if not fil or not fil.filename:
            return jsonify({'ok': False, 'err': 'avatar file required'}), 400

        ext = fext(fil.filename)
        if ext not in avex:
            return jsonify({'ok': False, 'err': 'allowed: jpg,jpeg,png,webp,gif'}), 400

        os.makedirs(avdir, exist_ok=True)
        name = f'u{uid}_{uuid.uuid4().hex}.{ext}'
        path = os.path.join(avdir, name)
        fil.save(path)
        aurl = f'/api/avatar/{name}'

        s = db_session.get_sess()
        try:
            usr = s.get(User, uid)
            if not usr:
                return jsonify({'ok': False, 'err': 'user not found'}), 404
            usr.avatar = aurl
            s.commit()
            out = uout(usr)
        finally:
            s.close()

        push_user(uid, out)

        return jsonify({'ok': True, 'user': out})

    @app.route('/register', methods=['POST'])
    @app.route('/api/register', methods=['POST'])
    def reg():
        dat = request.get_json(silent=True) or {}
        uname = (dat.get('username') or '').strip().lower()
        pws = dat.get('password') or ''
        name = (dat.get('name') or '').strip() or uname
        mail = (dat.get('email') or '').strip().lower() or f'{uname}@local'

        if not uname or not pws:
            return jsonify({'ok': False, 'err': 'username,password required'}), 400
        if len(uname) < 3 or len(uname) > 32:
            return jsonify({'ok': False, 'err': 'username len 3..32'}), 400
        if any(ch.isspace() for ch in uname):
            return jsonify({'ok': False, 'err': 'username without spaces'}), 400

        s = db_session.get_sess()
        try:
            if s.query(User).filter(User.username == uname).first():
                return jsonify({'ok': False, 'err': 'username exists'}), 409
            if s.query(User).filter(User.email == mail).first():
                return jsonify({'ok': False, 'err': 'email exists'}), 409

            usr = User(name=name, username=uname, email=mail)
            usr.set_pw(pws)
            s.add(usr)
            s.commit()
            tok = tokmk(usr)
            return jsonify({'ok': True, 'user': uout(usr), 'token': tok}), 201
        finally:
            s.close()

    @app.route('/login', methods=['POST'])
    @app.route('/api/login', methods=['POST'])
    def log():
        dat = request.get_json(silent=True) or {}
        lval = (dat.get('login') or dat.get('email') or dat.get('username') or '').strip().lower()
        pws = dat.get('password') or ''

        if not lval or not pws:
            return jsonify({'ok': False, 'err': 'login,password required'}), 400

        s = db_session.get_sess()
        try:
            usr = s.query(User).filter(or_(User.email == lval, User.username == lval)).first()
            if not usr or not usr.chk_pw(pws):
                return jsonify({'ok': False, 'err': 'bad creds'}), 401
            if not (usr.username or '').strip():
                return jsonify({'ok': False, 'err': 'username required'}), 403
            tok = tokmk(usr)
            return jsonify({'ok': True, 'user': uout(usr), 'token': tok})
        finally:
            s.close()

    @app.route('/me', methods=['GET'])
    @app.route('/api/me', methods=['GET'])
    def me():
        uid = requid(ctok)
        if uid <= 0:
            return jsonify({'ok': False, 'err': 'unauthorized'}), 401
        s = db_session.get_sess()
        try:
            usr = s.get(User, uid)
            if not usr:
                return jsonify({'ok': False, 'err': 'unauthorized'}), 401
            return jsonify({'ok': True, 'user': uout(usr)})
        finally:
            s.close()

    @app.route('/profile', methods=['POST'])
    @app.route('/api/profile', methods=['POST'])
    def profile_upd():
        uid = requid(ctok)
        if uid <= 0:
            return jsonify({'ok': False, 'err': 'unauthorized'}), 401
        dat = request.get_json(silent=True) or {}
        s = db_session.get_sess()
        try:
            usr = s.get(User, uid)
            if not usr:
                return jsonify({'ok': False, 'err': 'unauthorized'}), 401

            name = (dat.get('name') or '').strip()
            bio = (dat.get('bio') or '').strip()
            phone = (dat.get('phone') or '').strip()
            uname = (dat.get('username') or '').strip().lower()

            if name:
                usr.name = name[:64]
            usr.bio = bio[:280]
            usr.phone = phone[:32]

            if uname:
                if len(uname) < 3 or len(uname) > 32:
                    return jsonify({'ok': False, 'err': 'username len 3..32'}), 400
                if any(ch.isspace() for ch in uname):
                    return jsonify({'ok': False, 'err': 'username without spaces'}), 400
                got = s.query(User).filter(User.username == uname, User.id != uid).first()
                if got:
                    return jsonify({'ok': False, 'err': 'username exists'}), 409
                usr.username = uname

            s.commit()
            out = uout(usr)
        finally:
            s.close()

        push_user(uid, out)
        return jsonify({'ok': True, 'user': out})

    @app.route('/users/<string:uname>', methods=['GET'])
    @app.route('/api/users/<string:uname>', methods=['GET'])
    def user_pub(uname):
        un = (uname or '').strip().lower()
        if not un:
            return jsonify({'ok': False, 'err': 'username required'}), 400
        s = db_session.get_sess()
        try:
            usr = s.query(User).filter(User.username == un).first()
            if not usr:
                return jsonify({'ok': False, 'err': 'not found'}), 404
            return jsonify({'ok': True, 'user': uout(usr)})
        finally:
            s.close()

    @app.route('/ws-ready', methods=['GET'])
    @app.route('/api/ws-ready', methods=['GET'])
    def wrdy():
        return jsonify({
            'ok': True,
            'ws': '/api/ws',
            'acts': [
                'auth',
                'search_users',
                'open_dm',
                'create_chat',
                'chat_add',
                'chat_setadm',
                'chat_kick',
                'chat_delself',
                'recent_chats',
                'get_chats',
                'get_msgs',
                'send_msg',
                'presence',
                'presence_bulk',
                'call_start',
                'call_acc',
                'call_rej',
                'call_end',
                'call_offer',
                'call_ice',
                'call_hist',
            ],
            'err': None,
        })

    @app.route('/<path:path>', methods=['GET'])
    def spa(path):
        if not has_front():
            return jsonify({'ok': False, 'err': 'frontend missing'}), 404
        if path.startswith('api/') or path.startswith('avatar/') or path.startswith('ws'):
            return jsonify({'ok': False, 'err': 'not found'}), 404
        if app.static_folder:
            full = os.path.join(app.static_folder, path)
            if os.path.isfile(full):
                return app.send_static_file(path)
        leaf = path.rsplit('/', 1)[-1]
        if '.' in leaf:
            return jsonify({'ok': False, 'err': 'not found'}), 404
        return app.send_static_file('index.html')
