import datetime as dt
import sqlalchemy as sa
from sqlalchemy import orm
from .db_session import Base


class Chat(Base):
    __tablename__ = 'chats'

    id = sa.Column(sa.Integer, primary_key=True, autoincrement=True)
    title = sa.Column(sa.String, nullable=False)
    is_grp = sa.Column(sa.Boolean, default=False)
    kind = sa.Column(sa.String, nullable=False, default='dm')  # dm|group|channel
    owner_id = sa.Column(sa.Integer, sa.ForeignKey('users.id'), nullable=True, index=True)
    cdt = sa.Column(sa.DateTime, default=dt.datetime.now)

    users = orm.relationship('User', secondary='chat_members', back_populates='chats')
    msgs = orm.relationship('Message', back_populates='chat', cascade='all, delete-orphan')
