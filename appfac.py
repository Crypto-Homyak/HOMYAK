from flask import Flask
from flask_sock import Sock

from conf import akey, ctok


def mkapp():
    app = Flask(
        __name__,
        static_folder='./templates/dist',
        template_folder='./templates/dist',
        static_url_path='',
    )
    app.config['SECRET_KEY'] = akey
    app.config.setdefault('AUTH_TOKEN_MAX_AGE_SEC', ctok)

    @app.after_request
    def cors(r):
        r.headers['Access-Control-Allow-Origin'] = '*'
        r.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
        r.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, PATCH, DELETE, OPTIONS'
        return r

    sk = Sock(app)
    return app, sk
