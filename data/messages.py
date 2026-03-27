import datetime as dt
import sqlalchemy as sa
from sqlalchemy import orm
from .db_session import Base


class Message(Base):
    __tablename__ = 'messages'

    id = sa.Column(sa.Integer, primary_key=True, autoincrement=True)
    txt = sa.Column(sa.String, nullable=False)
    cdt = sa.Column(sa.DateTime, default=dt.datetime.now)

    uid = sa.Column(sa.Integer, sa.ForeignKey('users.id'), nullable=False, index=True)
    cid = sa.Column(sa.Integer, sa.ForeignKey('chats.id'), nullable=False, index=True)

    user = orm.relationship('User', back_populates='msgs')
    chat = orm.relationship('Chat', back_populates='msgs')
