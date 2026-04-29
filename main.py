import os

from appfac import mkapp
from calls import mkhub
from conf import avdir
from data import db_session
from routes import bindrt
from wsapi import bindws

app, sk = mkapp()
hub = mkhub()

bindrt(app)
bindws(sk, hub)


if __name__ == '__main__':
    os.makedirs('db', exist_ok=True)
    os.makedirs(avdir, exist_ok=True)
    db_session.init_db('db/messenger.db')
    app.run(host='0.0.0.0', port=14080, debug=True)
