"""Clerk session verification and one-person workspace provisioning."""

from fastapi import APIRouter, Depends, HTTPException, Request
import jwt


router = APIRouter()

STARTER_CATEGORIES = (
    ("Salary", "income"),
    ("Other Income", "income"),
    ("Housing", "expense"),
    ("Food", "expense"),
    ("Transportation", "expense"),
    ("Utilities", "expense"),
    ("Healthcare", "expense"),
    ("Shopping", "expense"),
    ("Entertainment", "expense"),
    ("Other Expense", "expense"),
)


async def require_subject(request: Request) -> str:
    env = request.scope["env"]
    jwt_key = getattr(env, "CLERK_JWT_KEY", None)
    parties = getattr(env, "CLERK_AUTHORIZED_PARTIES", None)
    issuer = getattr(env, "CLERK_ISSUER", None)
    if not jwt_key or not parties or not issuer:
        raise HTTPException(status_code=503, detail="Sign-in is not configured")
    allowed = [part.strip() for part in parties.split(",") if part.strip()]
    if not allowed:
        raise HTTPException(status_code=503, detail="Sign-in is not configured")
    authorization = request.headers.get("authorization", "")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token or token.strip() != token:
        raise HTTPException(status_code=401, detail="Sign-in required")
    try:
        claims = jwt.decode(
            token,
            jwt_key.replace("\\n", "\n"),
            algorithms=["RS256"],
            issuer=issuer.rstrip("/"),
            options={"require": ["sub", "iss", "exp", "iat"], "verify_aud": False},
        )
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid session") from exc
    if claims.get("azp") not in allowed:
        raise HTTPException(status_code=401, detail="Invalid session")
    subject = claims.get("sub")
    if not isinstance(subject, str) or not subject.strip():
        raise HTTPException(status_code=401, detail="Sign-in required")
    return subject


async def require_workspace(request: Request, subject: str = Depends(require_subject)) -> int:
    conn = request.scope["env"].money_manager
    row = await (
        conn.prepare(
            "SELECT w.id FROM workspaces w JOIN users u ON u.id = w.owner_user_id "
            "WHERE u.auth_subject = ?"
        )
        .bind(subject)
        .first()
    )
    if row is None:
        raise HTTPException(status_code=409, detail="Workspace setup required")
    request.state.workspace_id = row["id"]
    return row["id"]


@router.post("/me/bootstrap")
async def bootstrap_workspace(request: Request, subject: str = Depends(require_subject)):
    conn = request.scope["env"].money_manager
    await conn.prepare("INSERT OR IGNORE INTO users (auth_subject) VALUES (?)").bind(subject).run()
    user = await conn.prepare("SELECT id FROM users WHERE auth_subject = ?").bind(subject).first()
    await (
        conn.prepare("INSERT OR IGNORE INTO workspaces (owner_user_id, name) VALUES (?, ?)")
        .bind(user["id"], "Personal")
        .run()
    )
    workspace = await (
        conn.prepare("SELECT id FROM workspaces WHERE owner_user_id = ?")
        .bind(user["id"])
        .first()
    )
    request.state.workspace_id = workspace["id"]
    count = await (
        conn.prepare("SELECT COUNT(*) AS count FROM categories WHERE workspace_id = ?")
        .bind(workspace["id"])
        .first()
    )
    if count["count"] == 0:
        for sequence, (name, type_) in enumerate(STARTER_CATEGORIES, start=1):
            await (
                conn.prepare(
                    "INSERT OR IGNORE INTO categories (workspace_id, name, type, sequence) VALUES (?, ?, ?, ?)"
                )
                .bind(workspace["id"], name, type_, sequence)
                .run()
            )
    return {"workspace_id": workspace["id"]}


@router.get("/me")
async def get_me(request: Request, workspace_id: int = Depends(require_workspace)):
    return {"workspace_id": workspace_id}
