"""Create the configured administrator once, with a password supplied on stdin."""
import sys
from sqlalchemy import select
from . import main
from .standalone import ADMIN_EMAIL

password = sys.stdin.read().rstrip('\r\n')
if not 12 <= len(password) <= 128:
    raise SystemExit('Administrator password must be 12–128 characters')
with main.SessionLocal() as db:
    if db.scalar(select(main.User).where(main.User.email == ADMIN_EMAIL)):
        raise SystemExit('Administrator already exists; password was not changed')
    user = main.User(email=ADMIN_EMAIL, password_hash=main.password_hasher.hash(password))
    db.add(user); db.commit()
print('Administrator created')
