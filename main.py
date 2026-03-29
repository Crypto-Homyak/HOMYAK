import json
import os

from flask import Flask, jsonify, render_template, request
from flask_sock import Sock

from data import db_session
from data.users import User

app = Flask(
    __name__,
    static_folder='./templates/dist',
    template_folder='./templates/dist',
    static_url_path=''
    )
app.config['SECRET_KEY'] = 'yandexlyceum_secret_key'

sk = Sock(app)


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/register', methods=['POST'])
def register():
    d = request.get_json(silent=True) or {}
    name = (d.get('name') or '').strip()
    email = (d.get('email') or '').strip().lower()
    pw = d.get('password') or ''

    if not name or not email or not pw:
        return jsonify({'ok': False, 'err': 'name,email,password required'}), 400

    s = db_session.get_sess()
    if s.query(User).filter(User.email == email).first():
        s.close()
        return jsonify({'ok': False, 'err': 'email exists'}), 409

    u = User(name=name, email=email)
    u.set_pw(pw)
    s.add(u)
    s.commit()

    out = {'ok': True, 'id': u.id, 'name': u.name, 'email': u.email}
    s.close()
    return jsonify(out), 201


@app.route('/login', methods=['POST'])
def login():
    d = request.get_json(silent=True) or {}
    email = (d.get('email') or '').strip().lower()
    pw = d.get('password') or ''

    if not email or not pw:
        return jsonify({'ok': False, 'err': 'email,password required'}), 400

    s = db_session.get_sess()
    u = s.query(User).filter(User.email == email).first()
    if not u or not u.chk_pw(pw):
        s.close()
        return jsonify({'ok': False, 'err': 'bad creds'}), 401

    out = {'ok': True, 'id': u.id, 'name': u.name, 'email': u.email}
    s.close()
    return jsonify(out)


@app.route('/ws-ready', methods=['GET'])
def ws_ready():
    return jsonify({'ok': True, 'ws': '/ws'})


@sk.route('/ws')
def ws(ws):
    ws.send(json.dumps({'ok': True, 'msg': 'ws up'}))
    while True:
        m = ws.receive()
        if m is None:
            break
        ws.send(json.dumps({'ok': True, 'echo': m}))


if __name__ == '__main__':
    os.makedirs('db', exist_ok=True)
    db_session.init_db('db/messenger.db')
    app.run(host='0.0.0.0', port=14080, debug=True)
