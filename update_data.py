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

    rows, refs, season = [], [], None
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
        ref = next((r.get("name") for r in (match.get("referees") or []) if r.get("type") == "REFEREE" and r.get("name")), None)
        refs.append(ref)

    scorers = []
    try:
        top = get(f"/competitions/{code}/scorers?limit=60")
        for item in top.get("scorers", []):
            team, player = item.get("team") or {}, item.get("player") or {}
            if not team.get("id"):
                continue
            scorers.append({
                "id": player.get("id"),
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

    squads = []
    try:
        data_teams = get(f"/competitions/{code}/teams")
        for team in data_teams.get("teams", []):
            if not team.get("id"):
                continue
            coach = (team.get("coach") or {}).get("name")
            players = []
            for p in team.get("squad") or []:
                if p.get("role") not in (None, "PLAYER"):
                    continue
                players.append({
                    "id": p.get("id"),
                    "n": p.get("name"),
                    "pos": p.get("position") or "",
                    "dob": (p.get("dateOfBirth") or "")[:10],
                    "nat": p.get("nationality") or "",
                    "num": p.get("shirtNumber"),
                })
            squads.append({"t": team_idx(team), "coach": coach, "players": players})
    except Exception as err:  # elencos são opcionais: a tabela continua funcionando
        print(f"  aviso: elencos de {code} indisponíveis ({err})")

    for team in teams:
        team.pop("id", None)
    return {"season": season_label(season), "teams": teams, "matches": rows, "refs": refs, "scorers": scorers, "squads": squads}



# ============ API-Football: lesionados e transferências (opcional) ============
AF_KEY = os.environ.get("API_FOOTBALL_KEY", "").strip()
AF_API = "https://v3.football.api-sports.io"
AF_LEAGUES = {"br": 71, "en": 39, "es": 140, "it": 135, "de": 78, "fr": 61}
AF_EVERY = 12 * 3600          # atualiza lesionados e transferências a cada 12 horas
AF_TRANSFER_BATCH = 18        # times por rodada (rodízio), para caber no limite grátis de 100/dia
AF_PLAYER_PAGES = 22          # páginas de estatísticas de jogadores por rodada (20 jogadores por página)


def af_get(path):
    for attempt in range(3):
        req = urllib.request.Request(AF_API + path, headers={"x-apisports-key": AF_KEY, "User-Agent": "radar-das-seis"})
        try:
            with urllib.request.urlopen(req, timeout=40) as resp:
                payload = json.load(resp)
            time.sleep(PAUSE)
            errs = payload.get("errors")
            if errs and (isinstance(errs, dict) and errs or isinstance(errs, list) and errs):
                raise RuntimeError(json.dumps(errs, ensure_ascii=False))
            return payload.get("response", [])
        except urllib.error.HTTPError as err:
            if err.code == 429:
                time.sleep(65)
                continue
            raise
    raise RuntimeError("Sem resposta da API-Football para " + path)


def norm_tokens(name):
    import unicodedata
    n = unicodedata.normalize("NFD", name or "").encode("ascii", "ignore").decode().lower()
    stop = {"fc", "ac", "sc", "cf", "afc", "club", "de", "da", "do", "calcio", "sv", "ssc", "ss", "us", "acf", "rc", "cr", "se", "ec", "fbc", "fbpa", "af", "ca", "cd", "ud", "sd", "rcd", "tsg", "vfb", "vfl", "fsv", "bc", "ogc", "losc", "sco", "aj", "as", "es", "osc", "hac", "sb", "real", "1", "04", "05", "07", "29"}
    return {w for w in "".join(c if c.isalnum() else " " for c in n).split() if w and w not in stop}


def match_teams(ours, theirs):
    """ours: lista de nomes (football-data); theirs: {id: nome} (API-Football) -> {id: nome nosso}"""
    pairs = []
    for tid, tname in theirs.items():
        tt = norm_tokens(tname)
        for oname in ours:
            ot = norm_tokens(oname)
            inter = len(tt & ot)
            if inter:
                pairs.append((inter / max(1, len(ot)) + inter / max(1, len(tt)), tid, oname))
    pairs.sort(reverse=True)
    out, used = {}, set()
    for score, tid, oname in pairs:
        if tid in out or oname in used or score < 0.6:
            continue
        out[tid] = oname
        used.add(oname)
    return out


def season_start_year(label):
    return int(str(label or datetime.datetime.now(BRT).year)[:4])


def af_raw(path):
    req = urllib.request.Request(AF_API + path, headers={"x-apisports-key": AF_KEY, "User-Agent": "radar-das-seis"})
    with urllib.request.urlopen(req, timeout=40) as resp:
        payload = json.load(resp)
    time.sleep(PAUSE)
    return payload

def af_player_row(item, lid, idmap):
    p = item.get("player") or {}
    stats = [x for x in (item.get("statistics") or []) if (x.get("league") or {}).get("id") == lid]
    if not stats:
        return None
    # se jogou por dois times na mesma liga, fica o time onde mais atuou
    st = max(stats, key=lambda x: ((x.get("games") or {}).get("appearences") or 0))
    team = idmap.get(str((st.get("team") or {}).get("id")))
    if not team:
        return None
    tot = lambda path: sum(((x.get(path[0]) or {}).get(path[1]) or 0) for x in stats)
    g = st.get("games") or {}
    rating = None
    try:
        rating = round(float(g.get("rating")), 2) if g.get("rating") else None
    except (TypeError, ValueError):
        rating = None
    acc = (st.get("passes") or {}).get("accuracy")
    try:
        acc = int(acc) if acc is not None else None
    except (TypeError, ValueError):
        acc = None
    return {
        "n": p.get("name"), "fn": p.get("firstname"), "ln": p.get("lastname"), "age": p.get("age"), "nat": p.get("nationality"),
        "team": team, "pos": g.get("position"), "num": g.get("number"),
        "mp": tot(("games", "appearences")), "xi": tot(("games", "lineups")), "min": tot(("games", "minutes")), "rat": rating,
        "g": tot(("goals", "total")), "a": tot(("goals", "assists")), "gc": tot(("goals", "conceded")), "sv": tot(("goals", "saves")),
        "sh": tot(("shots", "total")), "sot": tot(("shots", "on")), "pas": tot(("passes", "total")), "kp": tot(("passes", "key")), "acc": acc,
        "tk": tot(("tackles", "total")), "blk": tot(("tackles", "blocks")), "int": tot(("tackles", "interceptions")),
        "du": tot(("duels", "total")), "duw": tot(("duels", "won")), "dra": tot(("dribbles", "attempts")), "drs": tot(("dribbles", "success")),
        "fc": tot(("fouls", "committed")), "fd": tot(("fouls", "drawn")), "yc": tot(("cards", "yellow")), "rc": tot(("cards", "red")),
        "ps": tot(("penalty", "scored")), "pm": tot(("penalty", "missed")), "psv": tot(("penalty", "saved")),
    }


def update_af_players(out, extra, af):
    """Estatísticas de todos os jogadores, em rodízio: algumas páginas por rodada, liga após liga."""
    keys = [k for k in AF_LEAGUES if out["leagues"].get(k)]
    if not keys:
        return
    pc = af.setdefault("players", {"i": 0, "page": 1})
    budget = AF_PLAYER_PAGES
    while budget > 0:
        key = keys[pc["i"] % len(keys)]
        league = out["leagues"][key]
        lid, season = AF_LEAGUES[key], season_start_year(league.get("season"))
        idmap = af.get("teams", {}).get(f"{key}:{season}")
        ex = extra.setdefault(key, {"inj": {}, "tr": {}})
        if not idmap:
            pc["i"] += 1; pc["page"] = 1
            if all(not af.get("teams", {}).get(f"{k}:{season_start_year(out['leagues'][k].get('season'))}") for k in keys):
                return
            continue
        try:
            payload = af_raw(f"/players?league={lid}&season={season}&page={pc['page']}")
            budget -= 1
            errs = payload.get("errors")
            if errs:
                raise RuntimeError(json.dumps(errs, ensure_ascii=False))
            pl = ex.setdefault("pl", {})
            for item in payload.get("response", []):
                row = af_player_row(item, lid, idmap)
                if row:
                    pl[str((item.get("player") or {}).get("id"))] = row
            total = (payload.get("paging") or {}).get("total") or 1
            if pc["page"] >= total:
                ex["plAt"] = datetime.datetime.now(BRT).isoformat(timespec="minutes")
                pc["i"] = (pc["i"] + 1) % len(keys); pc["page"] = 1
            else:
                pc["page"] += 1
        except Exception as err:
            af.setdefault("errors", {})[key + ":jogadores"] = str(err)[:300]
            print(f"  aviso API-Football jogadores {key}: {err}")
            pc["i"] = (pc["i"] + 1) % len(keys); pc["page"] = 1
            budget -= 1


def update_api_football(out, previous):
    extra = previous.get("extra", {}) if previous else {}
    af = extra.get("_af", {})
    now = time.time()
    if not AF_KEY:
        return extra
    if now - af.get("last", 0) < AF_EVERY:
        return extra
    af["last"] = now
    af["errors"] = {}
    today = datetime.datetime.now(BRT).date()
    for key, lid in AF_LEAGUES.items():
        league = out["leagues"].get(key)
        if not league:
            continue
        season = season_start_year(league.get("season"))
        ours = [t.get("full") or t.get("name") for t in league.get("teams", [])]
        ex = extra.setdefault(key, {"inj": {}, "tr": {}})
        try:
            cache = af.setdefault("teams", {})
            ck = f"{key}:{season}"
            if ck not in cache:
                resp = af_get(f"/teams?league={lid}&season={season}")
                theirs = {str(r["team"]["id"]): r["team"]["name"] for r in resp if r.get("team")}
                cache[ck] = match_teams(ours, theirs)
            idmap = cache[ck]
            # lesionados e suspensos: registros de jogos a partir de ontem = desfalques atuais
            resp = af_get(f"/injuries?league={lid}&season={season}")
            by_team = {}
            for r in resp:
                tid = str((r.get("team") or {}).get("id"))
                name = idmap.get(tid)
                if not name:
                    continue
                p, fx = r.get("player") or {}, r.get("fixture") or {}
                d = (fx.get("date") or "")[:10]
                by_team.setdefault(name, {}).setdefault(str(p.get("id")), []).append((d, p.get("name"), p.get("type"), p.get("reason")))
            inj = {}
            limit = (today - datetime.timedelta(days=1)).isoformat()
            for name, players in by_team.items():
                rows = []
                for pid, recs in players.items():
                    recs.sort()
                    if recs[-1][0] < limit:
                        continue  # já voltou a jogar
                    # sequência atual de jogos perdidos
                    since, missed = recs[-1][0], 0
                    for d, n, typ, reason in reversed(recs):
                        since = d
                        if d <= today.isoformat():
                            missed += 1
                    last = recs[-1]
                    rows.append({"n": last[1], "type": last[2], "reason": last[3], "since": since, "missed": missed, "next": last[0]})
                inj[name] = sorted(rows, key=lambda x: x["since"])
            ex["inj"] = inj
            ex["injAt"] = datetime.datetime.now(BRT).isoformat(timespec="minutes")
            # transferências em rodízio de times
            cur = af.setdefault("cursor", {}).get(key, 0)
            ids = sorted(idmap.keys())
            batch = ids[cur:cur + max(1, AF_TRANSFER_BATCH // len(AF_LEAGUES))]
            af["cursor"][key] = (cur + len(batch)) % max(1, len(ids))
            window_start = f"{season}-01-01" if key == "br" else f"{season}-06-01"
            for tid in batch:
                name = idmap[tid]
                resp = af_get(f"/transfers?team={tid}")
                ins, outs = [], []
                for r in resp:
                    pname = (r.get("player") or {}).get("name")
                    for t in r.get("transfers") or []:
                        d = (t.get("date") or "")[:10]
                        if d < window_start:
                            continue
                        tin, tout = (t.get("teams") or {}).get("in") or {}, (t.get("teams") or {}).get("out") or {}
                        row = {"n": pname, "date": d, "fee": t.get("type") or ""}
                        if str(tin.get("id")) == tid:
                            ins.append({**row, "club": tout.get("name")})
                        elif str(tout.get("id")) == tid:
                            outs.append({**row, "club": tin.get("name")})
                ex["tr"][name] = {"in": sorted(ins, key=lambda x: x["date"], reverse=True), "out": sorted(outs, key=lambda x: x["date"], reverse=True),
                                  "at": datetime.datetime.now(BRT).isoformat(timespec="minutes")}
        except Exception as err:  # não derruba a atualização principal
            af["errors"][key] = str(err)[:300]
            print(f"  aviso API-Football {key}: {err}")
    try:
        update_af_players(out, extra, af)
    except Exception as err:
        print(f"  aviso API-Football jogadores: {err}")
    extra["_af"] = af
    return extra


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
    out = {
        "updated": datetime.datetime.now(BRT).isoformat(timespec="seconds"),
        "source": "football-data.org",
        "leagues": leagues,
    }
    extra = update_api_football(out, previous)
    if extra:
        out["extra"] = extra
    same_leagues = previous.get("leagues") and digest(previous["leagues"]) == digest(leagues) and previous.get("source") == "football-data.org"
    same_extra = digest(previous.get("extra", {})) == digest(extra or {})
    if same_leagues and same_extra:
        print("Nada mudou desde a última atualização.")
        return
    if same_leagues:
        out["updated"] = previous.get("updated", out["updated"])
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, separators=(",", ":"))
    print("data.json atualizado.")


if __name__ == "__main__":
    main()
