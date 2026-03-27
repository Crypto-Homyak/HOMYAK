import sqlalchemy as sa
import sqlalchemy.orm as so
from sqlalchemy.orm import Session

Base = so.declarative_base()
_sf = None


def init_db(dbf):
    global _sf
    if _sf:
        return
    if not dbf or not dbf.strip():
        raise Exception('db path required')
    cs = f"sqlite:///{dbf.strip()}?check_same_thread=False"
    e = sa.create_engine(cs, echo=False)
    _sf = so.sessionmaker(bind=e)
    from . import __all_models
    Base.metadata.create_all(e)


def get_sess() -> Session:
    global _sf
    return _sf()
