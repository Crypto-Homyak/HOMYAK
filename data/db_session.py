import sqlalchemy as sa
import sqlalchemy.orm as so
from sqlalchemy.orm import Session

Base = so.declarative_base()
_sf = None
_eng = None


def _fix_users():
    global _eng
    if _eng is None:
        return

    ins = sa.inspect(_eng)
    if 'users' not in ins.get_table_names():
        return

    cols = {c['name'] for c in ins.get_columns('users')}
    if 'username' not in cols:
        with _eng.begin() as c:
            c.exec_driver_sql('ALTER TABLE users ADD COLUMN username VARCHAR')

    with _eng.begin() as c:
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

    with _eng.begin() as c:
        c.exec_driver_sql('CREATE UNIQUE INDEX IF NOT EXISTS ix_users_username ON users (username)')


def init_db(dbf):
    global _sf, _eng
    if _sf:
        return
    if not dbf or not dbf.strip():
        raise Exception('db path required')
    cs = f"sqlite:///{dbf.strip()}?check_same_thread=False"
    _eng = sa.create_engine(cs, echo=False)
    _sf = so.sessionmaker(bind=_eng)
    from . import __all_models
    Base.metadata.create_all(_eng)
    _fix_users()


def get_sess() -> Session:
    global _sf
    return _sf()
