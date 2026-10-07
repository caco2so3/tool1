from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel

from ..db import get_conn
from ..auth import (
    hash_password,
    verify_password,
    create_session,
    current_user,
    require_admin,
)

router = APIRouter()


class LoginIn(BaseModel):
    username: str
    password: str


class UserIn(BaseModel):
    username: str
    password: str
    role: str


class PasswordIn(BaseModel):
    password: str


@router.post("/login")
def login(data: LoginIn, response: Response):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id, password_hash, role, active FROM users WHERE username=?",
            (data.username,),
        ).fetchone()
    if not row or not row["active"] or not verify_password(data.password, row["password_hash"]):
        raise HTTPException(401, "invalid credentials")
    token = create_session(row["id"])
    response.set_cookie(
        "session",
        token,
        httponly=True,
        samesite="lax",
        path="/",
        max_age=60 * 60 * 24 * 365 * 10,
    )
    return {"ok": True, "role": row["role"], "username": data.username}


@router.post("/logout")
def logout(request: Request, response: Response):
    token = request.cookies.get("session")
    if token:
        with get_conn() as conn:
            conn.execute("DELETE FROM sessions WHERE token=?", (token,))
    response.delete_cookie("session", path="/")
    return {"ok": True}


@router.get("/me")
def me(user=Depends(current_user)):
    if not user:
        raise HTTPException(401)
    return user


@router.get("/users")
def list_users(user=Depends(require_admin)):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, username, role, active, created_at FROM users ORDER BY id"
        ).fetchall()
        return [dict(r) for r in rows]


@router.post("/users")
def create_user(u: UserIn, user=Depends(require_admin)):
    if u.role not in ("admin", "line"):
        raise HTTPException(400, "bad role")
    if len(u.password) < 4:
        raise HTTPException(400, "пароль слишком короткий")
    with get_conn() as conn:
        try:
            cur = conn.execute(
                "INSERT INTO users(username, password_hash, role, created_at) VALUES(?,?,?,?)",
                (
                    u.username.strip(),
                    hash_password(u.password),
                    u.role,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
        except Exception:
            raise HTTPException(400, "логин занят")
    return {"id": cur.lastrowid}


@router.put("/users/{uid}/password")
def set_password(uid: int, body: PasswordIn, user=Depends(require_admin)):
    if len(body.password) < 4:
        raise HTTPException(400, "короткий")
    with get_conn() as conn:
        conn.execute(
            "UPDATE users SET password_hash=? WHERE id=?",
            (hash_password(body.password), uid),
        )
    return {"ok": True}


@router.delete("/users/{uid}")
def deactivate_user(uid: int, user=Depends(require_admin)):
    if user["id"] == uid:
        raise HTTPException(400, "нельзя деактивировать себя")
    with get_conn() as conn:
        conn.execute("UPDATE users SET active=0 WHERE id=?", (uid,))
        conn.execute("DELETE FROM sessions WHERE user_id=?", (uid,))
    return {"ok": True}