#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json, time, sys, datetime as dt
from urllib.parse import quote
import ssl
import urllib.request
import urllib.error

# === MySQL driver: scegli UNO dei due import attivi (commenta l'altro) ===
# Consigliato: mysql-connector-python
import mysql.connector as mysql
# In alternativa: PyMySQL
# import pymysql as mysql

from pathlib import Path
CONFIG_PATH = Path(__file__).resolve().parent / "fpfood_sync.config.json"

def load_config(path):
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Config non trovato: {p}")
    with p.open("r", encoding="utf-8") as f:
        return json.load(f)

def http_get_json(url, timeout=20):
    # semplice GET senza dipendenze
    req = urllib.request.Request(url, headers={"Accept":"application/json"})
    ctx = ssl.create_default_context()
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
        raw = r.read().decode("utf-8", errors="replace")
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            raise RuntimeError(f"Non JSON da {url}: {raw[:200]}")

def to_datetime_day(date_str):
    # PWA invia "YYYY-MM-DD"
    y, m, d = map(int, date_str.split("-"))
    return dt.datetime(y, m, d, 0, 0, 0)

def month_floor(d):
    return dt.datetime(d.year, d.month, 1, 0, 0, 0)

def convenzione_and_sconto(ristorante, cfg):
    map_conv = cfg["mapping"]["ristorante_to_convenzione"]
    idconv = map_conv.get(ristorante, 2)  # default 2
    sconto = cfg["mapping"]["sconto_if_convenzione_1"] if idconv == 1 else cfg["mapping"]["sconto_else"]
    return idconv, float(sconto)

def fetch_all_fpfood(cfg):
    base = cfg["api_base"].rstrip("/")
    users = cfg["users"]
    timeout = int(cfg.get("timeout_seconds", 25))

    all_rows = []  # ogni item: dict con chiave logica e dati
    for uid in users:
        url = f"{base}/pasti/{quote(uid)}"
        try:
            items = http_get_json(url, timeout=timeout)
        except Exception as e:
            print(f"[WARN] GET {url} fallita: {e}")
            continue

        # normalizza struttura attesa:
        # { id, utente, ristorante, data (YYYY-MM-DD), importo }
        for it in items or []:
            try:
                d_giorno = to_datetime_day(str(it.get("data","")).strip())
            except Exception:
                # se data non valida salto
                continue
            idconv, sconto = convenzione_and_sconto(str(it.get("ristorante","")).strip(), cfg)
            row = {
                "IdUtente": str(it.get("utente_id", uid)).strip() or uid,   # se backend non manda utente_id uso uid
                "IdGiorno": d_giorno,
                "IdMese": month_floor(d_giorno),
                "Importo": float(it.get("importo", 0.0) or 0.0),
                "sconto": sconto,
                "IdConvenzione": int(idconv),
                # opzionali utili per trace
                "_ristorante": str(it.get("ristorante","")).strip(),
                "_source_id": it.get("id") or it.get("_id") or None
            }
            all_rows.append(row)
    return all_rows

def open_mysql(cfg):
    mc = cfg["mysql"]
    conn = mysql.connect(
        host=mc["host"], port=int(mc.get("port",3306)),
        user=mc["user"], password=mc["password"],
        database=mc["database"], charset=mc.get("charset","latin1")
    )
    try:
        cur = conn.cursor()
        cur.execute("SELECT DATABASE()")
        db = cur.fetchone()[0]
        print(f"[DB] connected to {db}.{cfg['mysql']['table']}")
        cur.close()
    except Exception as e:
        print(f"[DB] info error: {e}")
    return conn

def read_existing_map(conn, cfg):
    mc = cfg["mysql"]; tbl = mc["table"]
    sql = f"""SELECT IdUtente, IdGiorno, idpastiConsumati
                , Importo, sconto, IdConvenzione
                , IdMese
              FROM {tbl}"""
    cur = conn.cursor()
    cur.execute(sql)
    rows = cur.fetchall()
    cur.close()
    # mappa chiave logica -> record
    # chiave = (IdUtente, IdGiorno.date())
    existing = {}
    for (IdUtente, IdGiorno, idpk, Importo, sconto, IdConvenzione, IdMese) in rows:
        k = (str(IdUtente), IdGiorno.date())
        existing[k] = {
            "idpk": idpk,
            "Importo": float(Importo or 0.0),
            "sconto": float(sconto or 0.0),
            "IdConvenzione": int(IdConvenzione or 0),
            "IdMese": IdMese
        }
    return existing

def upsert_delete(conn, cfg, fp_rows):
    mc = cfg["mysql"]; tbl = mc["table"]
    existing = read_existing_map(conn, cfg)

    # build desired map from FP rows
    desired = {}
    for r in fp_rows:
        k = (r["IdUtente"], r["IdGiorno"].date())
        desired[k] = r  # ultimo vince; per stesso giorno utente vale l’ultimo letto

    ins = 0; upd = 0; dele = 0

    # INSERT / UPDATE
    cur = conn.cursor()
    for k, r in desired.items():
        if k in existing:
            ex = existing[k]
            need_upd = (
                round(ex["Importo"],5) != round(r["Importo"],5) or
                round(ex["sconto"],5)  != round(r["sconto"],5)  or
                int(ex["IdConvenzione"]) != int(r["IdConvenzione"]) or
                ex["IdMese"].date() != r["IdMese"].date()
            )
            if need_upd:
                sql = f"""UPDATE {tbl}
                 SET Importo=%s, sconto=%s, IdConvenzione=%s, IdMese=%s, OrigineFP=1
                 WHERE idpastiConsumati=%s"""
                cur.execute(sql, (
                    r["Importo"], r["sconto"], r["IdConvenzione"], r["IdMese"],
                    ex["idpk"]
                ))
                upd += 1
        else:
            sql = f"""INSERT INTO {tbl}
             (IdUtente, IdMese, IdGiorno, Importo, sconto, IdConvenzione, OrigineFP)
             VALUES (%s,%s,%s,%s,%s,%s,%s)"""
            cur.execute(sql, (
                r["IdUtente"], r["IdMese"], r["IdGiorno"],
                r["Importo"], r["sconto"], r["IdConvenzione"],
                1
            ))
            ins += 1

    # DELETE mancanti
    if cfg.get("delete_missing", True):
        for k, ex in existing.items():

            # Controlla SE la riga proviene da FPFOOD
            sql_chk = f"SELECT OrigineFP FROM {tbl} WHERE idpastiConsumati=%s"
            cur.execute(sql_chk, (ex["idpk"],))
            row = cur.fetchone()

            if not row:
                continue

            origine = row[0]

            # Se OrigineFP è NULL → riga STORICA → NON cancellare MAI
            if origine is None:
                continue

            # Se non è 1 → NON è FPFOOD → NON toccare
            if origine != 1:
                continue

            # Ora è sicuro: riga FPFOOD che NON esiste più nel backend locale
            if k not in desired:
                sql = f"DELETE FROM {tbl} WHERE idpastiConsumati=%s"
                cur.execute(sql, (ex["idpk"],))
                dele += 1

    conn.commit()
    cur.close()
    return ins, upd, dele

def run_once(cfg):
    print("[SYNC] start full-sync")
    rows = fetch_all_fpfood(cfg)
    print(f"[SYNC] letti {len(rows)} pasti da FPFood")

    # === SAFETY CHECK: se FPFood non risponde / restituisce 0 righe → NON toccare MySQL ===
    if len(rows) == 0:
        print("[SYNC] ABORT: zero pasti ricevuti → nessun INS/UPD/DEL eseguito")
        return

    conn = open_mysql(cfg)
    try:
        i, u, d = upsert_delete(conn, cfg, rows)
        print(f"[SYNC] done: INS={i} UPD={u} DEL={d}")
    finally:
        conn.close()

def main():
    cfg = load_config(CONFIG_PATH)
    run_once(cfg)
    sch = cfg.get("scheduler", {})
    if not sch.get("enabled", False):
        return
    interval = int(sch.get("interval_seconds", 300))
    print(f"[SCHED] attivo — ogni {interval} sec")
    while True:
        time.sleep(interval)
        try:
            run_once(cfg)
        except Exception as e:
            print(f"[ERR] ciclo sync: {e}")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)