import pathlib, py_compile, traceback

ROOT = pathlib.Path(__file__).resolve().parent
FILES = [
    "app/main.py",
    "app/core/config.py",
    "app/core/rate_limiter.py",
    "app/core/security.py",
    "app/db/session.py",
    "app/models/user.py",
    "app/models/project.py",
    "app/repositories/user_repository.py",
    "app/services/auth_service.py",
    "app/schemas/user.py",
    "app/api/v1/endpoints/health.py",
    "app/api/v1/endpoints/auth.py",
    "app/api/v1/router.py",
    "app/api/router.py",
    "alembic/versions/b3c4d5e6f708_add_user_email_verification.py",
]
lines = []
for f in FILES:
    try:
        py_compile.compile(str(ROOT / f), doraise=True)
        lines.append("OK   " + f)
    except Exception as e:  # noqa
        lines.append("ERR  " + f + ": " + e.__class__.__name__ + ": " + str(e).splitlines()[0])

try:
    import app.main
    routes = sorted(
        r.path
        for r in app.main.app.routes
        if hasattr(r, "route") and r.path
    )
    lines.append("IMPORT OK")
    lines.append("routes: " + ", ".join(routes))
except Exception as e:  # noqa
    lines.append("IMPORT ERR: " + repr(e))
    tb = traceback.format_exc().splitlines()
    lines.extend(tb[-6:])

pathlib.Path(ROOT / "_diag_out.txt").write_text("\n".join(lines), encoding="utf-8")
