import datetime as dt
import sqlalchemy as sa
from .db_session import Base


class CallLog(Base):
    __tablename__ = 'call_logs'

    id = sa.Column(sa.Integer, primary_key=True, autoincrement=True)
    cid = sa.Column(sa.String, nullable=False, index=True)
    chat_id = sa.Column(sa.Integer, sa.ForeignKey('chats.id'), nullable=False, index=True)
    caller_id = sa.Column(sa.Integer, sa.ForeignKey('users.id'), nullable=False, index=True)
    callee_id = sa.Column(sa.Integer, sa.ForeignKey('users.id'), nullable=False, index=True)
    status = sa.Column(sa.String, nullable=False, default='ringing')  # ringing|talk|rejected|missed|ended
    duration = sa.Column(sa.Integer, nullable=False, default=0)
    started = sa.Column(sa.DateTime, default=dt.datetime.now)
    accepted = sa.Column(sa.DateTime, nullable=True)
    ended = sa.Column(sa.DateTime, nullable=True)
