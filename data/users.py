import datetime as dt
import sqlalchemy as sa
from sqlalchemy import orm
from werkzeug.security import check_password_hash, generate_password_hash

from .db_session import Base


class User(Base):
    __tablename__ = 'users'

    id = sa.Column(sa.Integer, primary_key=True, autoincrement=True)
    name = sa.Column(sa.String, nullable=False)
    email = sa.Column(sa.String, unique=True, index=True, nullable=False)
    hp = sa.Column(sa.String, nullable=False)
    cdt = sa.Column(sa.DateTime, default=dt.datetime.now)

    chats = orm.relationship('Chat', secondary='chat_members', back_populates='users')
    msgs = orm.relationship('Message', back_populates='user')

    def set_pw(self, pw):
        self.hp = generate_password_hash(pw)

    def chk_pw(self, pw):
        return check_password_hash(self.hp, pw)
