"""Study enrollment: link an extension install to a study code (P01-XXXX).

Wire into main.py with two lines:
    from participants import router as participants_router
    app.include_router(participants_router)

Flow:
  1. Team runs `python make_codes.py 10` and hands out codes.
  2. Participant opens the extension popup and enters their code.
  3. First time: the code is claimed by that install's token.
     Reinstall / second computer: the code already has a token, so this install
     ADOPTS that token and anything it captured so far is merged into it.
"""

import os
from datetime import date

import psycopg
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

DB_URL = os.environ.get("DATABASE_URL", "postgresql://mirror:mirror@localhost/algorithm_mirror")
router = APIRouter()


class EnrollIn(BaseModel):
    code: str
    userToken: str


def _phase(row, today: date | None = None) -> str | None:
    baseline, treatment, washout, end = row
    today = today or date.today()
    if end and today > end:
        return "finished"
    if washout and today >= washout:
        return "washout"
    if treatment and today >= treatment:
        return "treatment"
    if baseline and today >= baseline:
        return "baseline"
    return "not started" if baseline else None


@router.post("/enroll")
def enroll(body: EnrollIn):
    code = body.code.strip().upper()
    token = body.userToken.strip()
    if not code or not token:
        return JSONResponse({"error": "Enter your study code."}, status_code=400)

    with psycopg.connect(DB_URL) as conn, conn.cursor() as cur:
        # This install already belongs to a different code?
        cur.execute("SELECT study_code FROM participants WHERE user_token = %s", (token,))
        other = cur.fetchone()
        if other and other[0] != code:
            return JSONResponse({"error": f"This browser is already enrolled as {other[0]}."}, status_code=409)

        cur.execute("SELECT user_token FROM participants WHERE study_code = %s FOR UPDATE", (code,))
        row = cur.fetchone()
        if not row:
            return JSONResponse({"error": "That code wasn't found. Check it with your study team."}, status_code=404)

        claimed, merged = row[0], 0
        if claimed is None:
            cur.execute("UPDATE participants SET user_token = %s, enrolled_at = now() WHERE study_code = %s",
                        (token, code))
            final = token
        elif claimed == token:
            final = token
        else:
            # Reinstall or second computer: fold this install's data into the existing participant.
            cur.execute(
                """DELETE FROM impressions a USING impressions b
                   WHERE a.user_token = %s AND b.user_token = %s
                     AND a.item_id = b.item_id AND a.entered_at = b.entered_at""",
                (token, claimed),
            )
            cur.execute("UPDATE impressions SET user_token = %s WHERE user_token = %s", (claimed, token))
            merged = cur.rowcount
            final = claimed

    print(f"[enroll] {code} token={final[:8]} merged={merged}")
    return {"studyCode": code, "userToken": final, "merged": merged}


@router.get("/users/{token}/participant")
def participant(token: str):
    with psycopg.connect(DB_URL) as conn, conn.cursor() as cur:
        cur.execute(
            """SELECT study_code, baseline_start, treatment_start, washout_start, end_date
               FROM participants WHERE user_token = %s""",
            (token,),
        )
        row = cur.fetchone()
    if not row:
        return {"enrolled": False}
    code, *dates = row
    return {
        "enrolled": True,
        "studyCode": code,
        "phase": _phase(dates),
        "dates": {k: (d.isoformat() if d else None)
                  for k, d in zip(("baseline_start", "treatment_start", "washout_start", "end_date"), dates)},
    }