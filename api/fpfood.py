# api/fpfood.py
# Backend FPFood — FastAPI + SQLite (CRUD pasti + totale per utente)
# Avvio: uvicorn api.fpfood:app --reload --host 0.0.0.0 --port 8000

from __future__ import annotations
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import List
import sqlite3
from pathlib import Path
from datetime import date

# ---------------------------------------
# Config DB (SQLite locale in ./data)
# ---------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent
DB_DIR = BASE_DIR / "data"
DB_DIR.mkdir(exist_ok=True)
DB_PATH = DB_DIR / "fpfood.db"
print("[DB] usando:", DB_PATH)

def _get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def _init_db():
    with _get_conn() as con:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS pasti (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                utente TEXT NOT NULL,
                ristorante TEXT NOT NULL,
                data TEXT NOT NULL,       -- ISO yyyy-mm-dd
                importo REAL NOT NULL     -- 2 decimali
            );
            """
        )
        con.commit()

_init_db()

# ---------------------------------------
# Modelli Pydantic (request/response)
# ---------------------------------------
RISTORANTI = ["Orto dei longobardi", "Sace Group"]

class PastoCreate(BaseModel):
    utente: str = Field(..., min_length=1, max_length=64, description="Nome Cognome, lato client memorizzato in LocalStorage")
    ristorante: str = Field(..., description="Valore tra: Orto dei longobardi | Sace Group")
    data: date
    importo: float = Field(..., ge=0, le=10_000)

class Pasto(PastoCreate):
    id: int

class TotaleResp(BaseModel):
    utente: str
    totale: float

# ---------------------------------------
# App FastAPI + CORS (sviluppo)
# ---------------------------------------
app = FastAPI(title="FPFood API", version="1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # in produzione: sostituisci con il tuo dominio
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------
# Helpers semplici
# ---------------------------------------
def _validate_ristorante(val: str):
    if val not in RISTORANTI:
        raise HTTPException(status_code=400, detail=f"Ristorante non valido. Ammessi: {', '.join(RISTORANTI)}")

def _row_to_pasto(row: sqlite3.Row) -> Pasto:
    return Pasto(
        id=row["id"],
        utente=row["utente"],
        ristorante=row["ristorante"],
        data=row["data"],
        importo=row["importo"],
    )

# ---------------------------------------
# Endpoints
# ---------------------------------------
@app.get("/api/ristoranti", response_model=List[str])
def get_ristoranti():
    # Fissi, come richiesto
    return RISTORANTI

@app.post("/api/pasti", response_model=Pasto)
def crea_pasto(p: PastoCreate):
    _validate_ristorante(p.ristorante)
    with _get_conn() as con:
        cur = con.execute(
            "INSERT INTO pasti (utente, ristorante, data, importo) VALUES (?, ?, ?, ?)",
            (p.utente.strip(), p.ristorante, p.data.isoformat(), float(p.importo)),
        )
        con.commit()
        new_id = cur.lastrowid
        row = con.execute("SELECT * FROM pasti WHERE id = ?", (new_id,)).fetchone()
        return _row_to_pasto(row)

@app.get("/api/pasti/{utente}", response_model=List[Pasto])
def lista_pasti(utente: str):
    with _get_conn() as con:
        rows = con.execute(
            "SELECT * FROM pasti WHERE utente = ? ORDER BY date(data) DESC, id DESC",
            (utente.strip(),)
        ).fetchall()
        return [_row_to_pasto(r) for r in rows]

@app.put("/api/pasti/{pasto_id}", response_model=Pasto)
def modifica_pasto(pasto_id: int, p: PastoCreate):
    _validate_ristorante(p.ristorante)
    with _get_conn() as con:
        print("[PUT] id=", pasto_id)
        exists = con.execute("SELECT 1 FROM pasti WHERE id = ?", (pasto_id,)).fetchone()
        print("[PUT] exists=", bool(exists))
        if not exists:
            raise HTTPException(status_code=404, detail="Pasto non trovato")
        con.execute(
         "UPDATE pasti SET utente=?, ristorante=?, data=?, importo=? WHERE id=?",
         (p.utente.strip(), p.ristorante, p.data.isoformat(), float(p.importo), int(pasto_id)),
        )
        con.commit()
        row = con.execute("SELECT * FROM pasti WHERE id = ?", (pasto_id,)).fetchone()
        return _row_to_pasto(row)

@app.delete("/api/pasti/{pasto_id}")
def elimina_pasto(pasto_id: int):
    with _get_conn() as con:
        print("[DEL] id=", pasto_id)
        cur = con.execute("DELETE FROM pasti WHERE id = ?", (pasto_id,))
        print("[DEL] rowcount=", cur.rowcount)
        con.commit()
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Pasto non trovato")
        return {"ok": True}

@app.get("/api/pasti/{utente}/totale", response_model=TotaleResp)
def totale_pasti(utente: str):
    with _get_conn() as con:
        row = con.execute(
            "SELECT COALESCE(SUM(importo), 0) as tot FROM pasti WHERE utente = ?",
            (utente.strip(),)
        ).fetchone()
        tot = float(row["tot"] if row and row["tot"] is not None else 0.0)
        return TotaleResp(utente=utente.strip(), totale=round(tot, 2))