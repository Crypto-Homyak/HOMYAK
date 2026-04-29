import sqlalchemy as sa
import sqlalchemy.orm as so
from sqlalchemy.orm import Session

Base = so.declarative_base()
sfac = None
eng = None


def fixuser():
    global eng
    if eng is None:
        return

    ins = sa.inspect(eng)
    if 'users' not in ins.get_table_names():
        return

    cols = {c['name'] for c in ins.get_columns('users')}
    if 'username' not in cols:
        with eng.begin() as c:
            c.exec_driver_sql('ALTER TABLE users ADD COLUMN username VARCHAR')
    if 'avatar' not in cols:
        with eng.begin() as c:
            c.exec_driver_sql("ALTER TABLE users ADD COLUMN avatar VARCHAR DEFAULT ''")

    with eng.begin() as c:
        rows = c.exec_driver_sql('SELECT id, email, name, username FROM users').fetchall()
        used = set()
        for r in rows:
            u = (r[3] or '').strip().lower()
            if u:
                used.add(u)
        for r in rows:
            uid = r[0]
            u = (r[3] or '').strip()
            if u:
                continue
            em = (r[1] or '').strip().lower()
            nm = (r[2] or '').strip().lower()
            base = 'user'
            if em and '@' in em:
                base = em.split('@')[0]
            elif nm:
                base = ''.join(ch for ch in nm if ch.isalnum() or ch in '._') or 'user'
            cand = base
            i = 1
            while cand.lower() in used:
                i += 1
                cand = f'{base}{i}'
            used.add(cand.lower())
            c.exec_driver_sql('UPDATE users SET username = ? WHERE id = ?', (cand, uid))

    with eng.begin() as c:
        c.exec_driver_sql('CREATE UNIQUE INDEX IF NOT EXISTS ix_users_username ON users (username)')


def fixcmm():
    global eng
    if eng is None:
        return

    ins = sa.inspect(eng)
    tables = set(ins.get_table_names())
    if 'chats' in tables:
        chat_cols = {c['name'] for c in ins.get_columns('chats')}
        if 'kind' not in chat_cols:
            with eng.begin() as c:
                c.exec_driver_sql("ALTER TABLE chats ADD COLUMN kind VARCHAR DEFAULT 'dm'")
        if 'owner_id' not in chat_cols:
            with eng.begin() as c:
                c.exec_driver_sql('ALTER TABLE chats ADD COLUMN owner_id INTEGER')
        with eng.begin() as c:
            c.exec_driver_sql(
                "UPDATE chats SET kind = CASE WHEN is_grp = 1 THEN 'group' ELSE 'dm' END WHERE kind IS NULL OR TRIM(kind) = ''"
            )

    if 'chat_members' in tables:
        cm_cols = {c['name'] for c in ins.get_columns('chat_members')}
        if 'role' not in cm_cols:
            with eng.begin() as c:
                c.exec_driver_sql("ALTER TABLE chat_members ADD COLUMN role VARCHAR DEFAULT 'member'")
        with eng.begin() as c:
            c.exec_driver_sql("UPDATE chat_members SET role = 'member' WHERE role IS NULL OR TRIM(role) = ''")

    if 'messages' in tables:
        msg_cols = {c['name'] for c in ins.get_columns('messages')}
        if 'kind' not in msg_cols:
            with eng.begin() as c:
                c.exec_driver_sql("ALTER TABLE messages ADD COLUMN kind VARCHAR DEFAULT 'text'")
        if 'meta' not in msg_cols:
            with eng.begin() as c:
                c.exec_driver_sql("ALTER TABLE messages ADD COLUMN meta VARCHAR DEFAULT ''")
        with eng.begin() as c:
            c.exec_driver_sql("UPDATE messages SET kind = 'text' WHERE kind IS NULL OR TRIM(kind) = ''")
            c.exec_driver_sql("UPDATE messages SET meta = '' WHERE meta IS NULL")


def init_db(dbf):
    global sfac, eng
    if sfac:
        return
    if not dbf or not dbf.strip():
        raise Exception('db path required')
    cs = f"sqlite:///{dbf.strip()}?check_same_thread=False"
    eng = sa.create_engine(cs, echo=False)
    sfac = so.sessionmaker(bind=eng)
    from . import __all_models
    Base.metadata.create_all(eng)
    fixuser()
    fixcmm()


def get_sess() -> Session:
    global sfac
    return sfac()
