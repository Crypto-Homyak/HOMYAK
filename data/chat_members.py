import datetime as dt
import sqlalchemy as sa
from .db_session import Base


class ChatMember(Base):
    __tablename__ = 'chat_members'

    id = sa.Column(sa.Integer, primary_key=True, autoincrement=True)
    uid = sa.Column(sa.Integer, sa.ForeignKey('users.id'), nullable=False, index=True)
    cid = sa.Column(sa.Integer, sa.ForeignKey('chats.id'), nullable=False, index=True)
    role = sa.Column(sa.String, nullable=False, default='member')  # member|admin
    cdt = sa.Column(sa.DateTime, default=dt.datetime.now)

    __table_args__ = (
        sa.UniqueConstraint('uid', 'cid', name='uq_uid_cid'),
    )
