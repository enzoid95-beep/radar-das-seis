#!/usr/bin/env python3
"""Radar das Seis — atualização automática dos dados.

Busca jogos e artilharia das seis ligas na API do football-data.org (v4)
e grava o arquivo data.json que o site lê. Só reescreve o arquivo quando
algum dado mudou, para não gerar commits vazios.

Uso: FOOTBALL_DATA_TOKEN=sua_chave python3 update_data.py
"""
import datetime
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.request

API = "https://api.football-data.org/v4"
TOKEN = os.environ.get("FOOTBALL_DATA_TOKEN", "").strip()
COMPETITIONS = {"br": "BSA", "en": "PL", "es": "PD", "it": "SA", "de": "BL1", "fr": "FL1"}
BRT = datetime.timezone(datetime.timedelta(hours=-3))  # horário de Brasília
PAUSE = 6.5  # plano gratuito: no máximo 10 requisições por minuto
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data.json")


def get(path):
    for attempt in range(5):
        req = urllib.request.Request(API + path, headers={"X-Auth-Token": TOKEN, "User-Agent": "radar-das-seis"})
        try:
            with urllib.request.urlopen(req, timeout=40) as resp:
                payload = json.load(resp)
            time.sleep(PAUSE)
            return payload
        except urllib.error.HTTPError as err:
            if err.code == 429:  # limite de requisições: espera e tenta de novo
                time.sleep(65)
                continue
            if err.code in (500, 502, 503, 504):
                time.sleep(15)
                continue
            raise
        except urllib.error.URLError:
            time.sleep(15)
    raise RuntimeError("Sem resposta da API para " + path)


def season_label(season):
    if not season:
        return None
    start, end = (season.get("startDate") or "")[:4], (season.get("endDate") or "")[:4]
    if not start:
        return None
    return start if start == end or not end else f"{start}/{end[2:]}"


def build_league(code):
    data = get(f"/competitions/{code}/matches")
    index, teams = {}, []

    def team_idx(team):
        tid = team["id"]
        if tid not in index:
            index[tid] = len(teams)
            teams.append({
                "id": tid,
                "name": team.get("shortName") or team.get("name"),
                "full": team.get("name"),
                "tla": team.get("tla") or "",
                "crest": team.get("crest") or "",
            })
        return index[tid]

    rows, season = [], None
    for match in data.get("matches", []):
        if match.get("stage") not in (None, "REGULAR_SEASON"):
            continue
        home, away = match.get("homeTeam") or {}, match.get("awayTeam") or {}
        if not home.get("id") or not away.get("id"):
            continue
        season = season or match.get("season")
        kickoff = datetime.datetime.fromisoformat(match["utcDate"].replace("Z", "+00:00")).astimezone(BRT)
        row = [match.get("matchday") or 0, kickoff.strftime("%Y-%m-%d"), kickoff.strftime("%H:%M"), team_idx(home), team_idx(away)]
        score = match.get("score") or {}
        full, half = score.get("fullTime") or {}, score.get("halfTime") or {}
        status = match.get("status")
        if status in ("FINISHED", "AWARDED") and full.get("home") is not None:
            row += [full["home"], full["away"], half.get("home"), half.get("away")]
        elif status in ("POSTPONED", "SUSPENDED", "CANCELLED"):
            row.append("adiado")
        rows.append(row)

    scorers = []
    try:
        top = get(f"/competitions/{code}/scorers?limit=60")
        for item in top.get("scorers", []):
            team, player = item.get("team") or {}, item.get("player") or {}
            if not team.get("id"):
                continue
            scorers.append({
                "n": player.get("name"),
                "t": team_idx(team),
                "pos": player.get("position") or player.get("section") or "",
                "nat": player.get("nationality") or "",
                "mp": item.get("playedMatches"),
                "g": item.get("goals") or 0,
                "a": item.get("assists") or 0,
                "p": item.get("penalties") or 0,
            })
    except Exception as err:  # artilharia é opcional: a tabela continua funcionando
        print(f"  aviso: artilharia de {code} indisponível ({err})")

    for team in teams:
        team.pop("id", None)
    return {"season": season_label(season), "teams": teams, "matches": rows, "scorers": scorers}


def digest(leagues):
    return hashlib.sha256(json.dumps(leagues, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def main():
    if not TOKEN:
        sys.exit("Defina a variável FOOTBALL_DATA_TOKEN com a sua chave do football-data.org.")
    previous = {}
    if os.path.exists(OUT):
        with open(OUT, encoding="utf-8") as fh:
            previous = json.load(fh)
    leagues = dict(previous.get("leagues", {}))
    failures = 0
    for key, code in COMPETITIONS.items():
        print(f"Atualizando {code}…")
        try:
            fresh = build_league(code)
            if not fresh["teams"]:
                raise RuntimeError("liga sem jogos na resposta")
            if not fresh["season"] and key in leagues:
                fresh["season"] = leagues[key].get("season")
            leagues[key] = fresh
        except Exception as err:  # mantém os dados anteriores dessa liga
            failures += 1
            print(f"  erro em {code}: {err} — mantendo os dados anteriores")
    if failures == len(COMPETITIONS):
        sys.exit("Nenhuma liga foi atualizada. Confira a chave da API.")
    if previous.get("leagues") and digest(previous["leagues"]) == digest(leagues) and previous.get("source") == "football-data.org":
        print("Nada mudou desde a última atualização.")
        return
    out = {
        "updated": datetime.datetime.now(BRT).isoformat(timespec="seconds"),
        "source": "football-data.org",
        "leagues": leagues,
    }
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, separators=(",", ":"))
    print("data.json atualizado.")


if __name__ == "__main__":
    main()
