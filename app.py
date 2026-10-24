import sqlite3
from collections import Counter
from datetime import date
from flask import Flask, render_template, request, redirect, url_for, flash, abort

app = Flask(__name__)
app.secret_key = "dev-only-change-later"   # needed for flash messages

# Keep this in sync with the CHECK list in schema.sql
DEATH_CAUSES = ["Executed", "By demon", "Own ability", "Other ability", "Survived", "Exiled"]

MINIMUM_GAMES = 1
MINIMUM_TOGETHER = 3

def get_db():
    conn = sqlite3.connect("clocktower.db")
    conn.row_factory = sqlite3.Row            # lets you use row["name"]
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def character_id(conn, name):
    """Return the id for a character name, or None if it doesn't exist."""
    row = conn.execute(
        "SELECT id FROM characters WHERE name = ?", (name.strip(),)
    ).fetchone()
    return row["id"] if row else None

def insert_players(conn, game_id, players):
    for name, start_c, start_a, end_c, end_a, death in players:
        name = name.strip()
        conn.execute("INSERT OR IGNORE INTO players (name) VALUES (?)", (name,))
        player_id = conn.execute(
            "SELECT id FROM players WHERE name = ?", (name,)
        ).fetchone()["id"]

        start_id = character_id(conn, start_c)
        end_id = character_id(conn, end_c) if end_c.strip() else start_id

        if start_id is None or end_id is None:
            raise ValueError(f"Unknown character for player '{name}'")

        conn.execute(
            "INSERT INTO game_players "
            "(game_id, player_id, start_character_id, start_alignment, "
            " end_character_id, end_alignment, death_cause) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (game_id, player_id, start_id, start_a,
             end_id, end_a or start_a, death or None),
        )


def win_streaks(conn):
    rows = conn.execute(
        "SELECT p.name, (gp.end_alignment = g.winning_team) AS won "
        "FROM game_players gp "
        "JOIN players p ON p.id = gp.player_id "
        "JOIN games g   ON g.id = gp.game_id "
        "ORDER BY g.date, g.id"
    ).fetchall()

    results_by_player = {}
    for r in rows:
        results_by_player.setdefault(r["name"], []).append(r["won"])

    streaks = {}
    for name, results in results_by_player.items():
        best_win = best_loss = cur_win = cur_loss = 0
        for won in results:
            if won:
                cur_win += 1
                cur_loss = 0
            else:
                cur_loss += 1
                cur_win = 0
            best_win = max(best_win, cur_win)
            best_loss = max(best_loss, cur_loss)
        streaks[name] = {"best_win": best_win, "best_loss": best_loss,
                         "cur_win": cur_win, "cur_loss": cur_loss}
    return streaks

def percent(part, whole):
    """Return part/whole as a percentage rounded to 1 decimal place."""
    if whole == 0:
        return None
    return round(100 * part / whole, 1)

@app.route("/", methods=["GET", "POST"])
def stat_page():
    conn = get_db()
    try:
        # ---- 1. Fetch the raw data (no calculations in SQL) ----
        games = conn.execute(
            "SELECT id, storyteller, winning_team FROM games"
        ).fetchall()

        entries = conn.execute(
            "SELECT p.id AS player_id, p.name AS player, "
            "       c.name AS character, c.type AS char_type, "
            "       gp.end_alignment, g.winning_team "
            "FROM game_players gp "
            "JOIN players p    ON p.id = gp.player_id "
            "JOIN characters c ON c.id = gp.start_character_id "
            "JOIN games g      ON g.id = gp.game_id"
        ).fetchall()

        # ---- 2. Headline numbers ----
        evil_wins = sum(1 for g in games if g["winning_team"] == "Evil")
        storytellers = {g["storyteller"] for g in games if g["storyteller"]}
        players_seen = {e["player"] for e in entries}

        headline = {
            "games": len(games),
            "players": len(players_seen),
            "storytellers": len(storytellers),
            "evil_winrate": percent(evil_wins, len(games)),
        }

        # ---- 3. Player stats ----
        # Build {"Tom K": {"games": 16, "wins": 11}, ...}
        player_totals = {}
        for e in entries:
            totals = player_totals.setdefault(e["player"], {
                "id": e["player_id"],
                "games": 0, "wins": 0,
                "good_games": 0, "good_wins": 0,
                "evil_games": 0, "evil_wins": 0,
            })
            won = e["end_alignment"] == e["winning_team"]

            totals["games"] += 1
            if won:
                totals["wins"] += 1

            if e["end_alignment"] == "Good":
                totals["good_games"] += 1
                if won:
                    totals["good_wins"] += 1
            else:
                totals["evil_games"] += 1
                if won:
                    totals["evil_wins"] += 1

        player_stats = []
        for name, totals in player_totals.items():
            if totals["games"] >= MINIMUM_GAMES:
                player_stats.append({
                    "id": totals["id"],
                    "name": name,
                    "games": totals["games"],
                    "wins": totals["wins"],
                    "winrate": percent(totals["wins"], totals["games"]),
                    "good_games": totals["good_games"],
                    "good_wins": totals["good_wins"],
                    "good_winrate": percent(totals["good_wins"], totals["good_games"]),
                    "evil_games": totals["evil_games"],
                    "evil_wins": totals["evil_wins"],
                    "evil_winrate": percent(totals["evil_wins"], totals["evil_games"]),
                })

        # Most games first; ties broken by higher winrate
        player_stats.sort(key=lambda p: (-p["games"], -p["winrate"]))

        # ---- 4. Character stats ----
        # Build {"Imp": {"type": "Demon", "plays": 11, "wins": 4}, ...}
        character_totals = {}
        for e in entries:
            totals = character_totals.setdefault(
                e["character"], {"type": e["char_type"], "plays": 0, "wins": 0}
            )
            totals["plays"] += 1
            if e["end_alignment"] == e["winning_team"]:
                totals["wins"] += 1

        character_rows = []
        for name, totals in character_totals.items():
            character_rows.append({
                "type": totals["type"],
                "name": name,
                "plays": totals["plays"],
                "winrate": percent(totals["wins"], totals["plays"]),
            })

        # Most played first; ties alphabetical
        character_rows.sort(key=lambda c: (-c["plays"], c["name"]))

        # Group into {"Townsfolk": [rows], "Demon": [rows], ...}
        characters_by_type = {}
        for c in character_rows:
            characters_by_type.setdefault(c["type"], []).append(c)

        return render_template(
            "stats.html",
            headline=headline,
            player_stats=player_stats,
            characters_by_type=characters_by_type,
            streaks=win_streaks(conn),
        )
    finally:
        conn.close()

@app.route("/add", methods=["GET", "POST"])
def add_game():
    conn = get_db()
    try:
        if request.method == "POST":
            f = request.form
            rows = zip(
                f.getlist("name"),
                f.getlist("start_char"),
                f.getlist("start_align"),
                f.getlist("end_char"),
                f.getlist("end_align"),
                f.getlist("death_cause"),
            )
            players = [r for r in rows if r[0].strip()]   # skip blank rows

            if not players:
                flash("Add at least one player.")
            else:
                try:
                    with conn:   # commits if all goes well, rolls back on error
                        cur = conn.execute(
                            "INSERT INTO games (date, script, storyteller, winning_team) "
                            "VALUES (?, ?, ?, ?)",
                            (f["date"], f["script"] or None,
                             f["storyteller"] or None, f["winning_team"]),
                        )
                        game_id = cur.lastrowid

                        insert_players(conn, game_id, players)
                    flash(f"Saved game #{game_id} with {len(players)} players.")
                    return redirect(url_for("add_game"))
                except (sqlite3.IntegrityError, ValueError) as e:
                    flash(f"Could not save: {e}")

        characters = conn.execute(
            "SELECT id, name FROM characters ORDER BY name"
        ).fetchall()
        return render_template(
            "add_game.html",
            characters=characters,
            death_causes=DEATH_CAUSES,
            today=date.today().isoformat(),
        )
    finally:
        conn.close()



@app.route("/games")
def list_games():
    conn = get_db()
    try:
        games = conn.execute(
            "SELECT g.id, g.date, g.script, g.storyteller, g.winning_team, "
            "       COUNT(gp.id) AS player_count "
            "FROM games g "
            "LEFT JOIN game_players gp ON gp.game_id = g.id "
            "GROUP BY g.id "
            "ORDER BY g.date DESC, g.id DESC"
        ).fetchall()
        return render_template("games.html", games=games)
    finally:
        conn.close()


@app.route("/games/<int:game_id>")
def game_detail(game_id):
    conn = get_db()
    try:
        game = conn.execute(
            "SELECT id, date, script, storyteller, winning_team "
            "FROM games WHERE id = ?",
            (game_id,),
        ).fetchone()

        if game is None:
            abort(404)   # shows a standard "Not Found" page

        players = conn.execute(
            "SELECT p.name, "
            "       sc.name AS start_char, gp.start_alignment, "
            "       ec.name AS end_char, gp.end_alignment, gp.death_cause "
            "FROM game_players gp "
            "JOIN players p     ON p.id  = gp.player_id "
            "JOIN characters sc ON sc.id = gp.start_character_id "
            "JOIN characters ec ON ec.id = gp.end_character_id "
            "WHERE gp.game_id = ? "
            "ORDER BY p.name",
            (game_id,),
        ).fetchall()

        return render_template("game_detail.html", game=game, players=players)
    finally:
        conn.close()


@app.route("/games/<int:game_id>/edit", methods=["GET", "POST"])
def edit_game(game_id):
    conn = get_db()
    try:
        game = conn.execute(
            "SELECT id, date, script, storyteller, winning_team "
            "FROM games WHERE id = ?",
            (game_id,),
        ).fetchone()
        if game is None:
            abort(404)

        if request.method == "POST":
            f = request.form
            rows = zip(
                f.getlist("name"),
                f.getlist("start_char"),
                f.getlist("start_align"),
                f.getlist("end_char"),
                f.getlist("end_align"),
                f.getlist("death_cause"),
            )
            players = [r for r in rows if r[0].strip()]

            if not players:
                flash("Add at least one player.")
            else:
                try:
                    with conn:
                        conn.execute(
                            "UPDATE games SET date = ?, script = ?, "
                            "storyteller = ?, winning_team = ? WHERE id = ?",
                            (f["date"], f["script"] or None,
                             f["storyteller"] or None, f["winning_team"],
                             game_id),
                        )
                        conn.execute(
                            "DELETE FROM game_players WHERE game_id = ?",
                            (game_id,),
                        )
                        insert_players(conn, game_id, players)
                    flash(f"Updated game #{game_id}.")
                    return redirect(url_for("game_detail", game_id=game_id))
                except (sqlite3.IntegrityError, ValueError) as e:
                    flash(f"Could not save: {e}")

        # GET (or a failed POST): load current data to fill the form
        players = conn.execute(
            "SELECT p.name, sc.name AS start_char, gp.start_alignment, "
            "       ec.name AS end_char, gp.end_alignment, gp.death_cause "
            "FROM game_players gp "
            "JOIN players p     ON p.id  = gp.player_id "
            "JOIN characters sc ON sc.id = gp.start_character_id "
            "JOIN characters ec ON ec.id = gp.end_character_id "
            "WHERE gp.game_id = ? ORDER BY gp.id",
            (game_id,),
        ).fetchall()
        characters = conn.execute(
            "SELECT id, name FROM characters ORDER BY name"
        ).fetchall()

        return render_template(
            "edit_game.html",
            game=game,
            players=players,
            characters=characters,
            death_causes=DEATH_CAUSES,
        )
    finally:
        conn.close()


@app.route("/games/<int:game_id>/delete", methods=["POST"])
def delete_game(game_id):
    conn = get_db()
    try:
        with conn:
            # Delete the child rows first, otherwise the foreign key blocks it
            conn.execute("DELETE FROM game_players WHERE game_id = ?", (game_id,))
            cur = conn.execute("DELETE FROM games WHERE id = ?", (game_id,))

        if cur.rowcount == 0:
            abort(404)   # no such game

        flash(f"Deleted game #{game_id}.")
        return redirect(url_for("list_games"))
    finally:
        conn.close()


@app.route("/player/<int:player_id>")
def player_page(player_id):
    conn = get_db()
    try:
        player = conn.execute(
            "SELECT id, name FROM players WHERE id = ?", (player_id,)
        ).fetchone()
        if player is None:
            abort(404)
        name = player["name"]

        # Every game this player was in, newest first
        rows = conn.execute(
            "SELECT g.id AS game_id, g.date, g.script, g.storyteller, g.winning_team, "
            "       sc.name AS start_char, gp.start_alignment, "
            "       ec.name AS end_char, gp.end_alignment, gp.death_cause "
            "FROM game_players gp "
            "JOIN games g       ON g.id  = gp.game_id "
            "JOIN characters sc ON sc.id = gp.start_character_id "
            "JOIN characters ec ON ec.id = gp.end_character_id "
            "WHERE gp.player_id = ? "
            "ORDER BY g.date DESC, g.id DESC",
            (player_id,),
        ).fetchall()

        if not rows:
            abort(404)

        # ---- Totals ----
        wins = good_games = good_wins = evil_games = evil_wins = survived = 0
        char_totals = {}          # {"Imp": {"plays": 3, "wins": 1}}
        death_counts = Counter()
        my_alignment = {}         # game id -> my end alignment
        i_won = {}                # game id -> True/False

        for r in rows:
            won = r["end_alignment"] == r["winning_team"]
            my_alignment[r["game_id"]] = r["end_alignment"]
            i_won[r["game_id"]] = won

            if won:
                wins += 1
            if r["end_alignment"] == "Good":
                good_games += 1
                good_wins += won
            else:
                evil_games += 1
                evil_wins += won

            if r["death_cause"] is None:
                survived += 1
            else:
                death_counts[r["death_cause"]] += 1

            c = char_totals.setdefault(r["start_char"], {"plays": 0, "wins": 0})
            c["plays"] += 1
            c["wins"] += won

        total = len(rows)
        summary = {
            "games": total,
            "wins": wins,
            "winrate": percent(wins, total),
            "good_games": good_games,
            "good_winrate": percent(good_wins, good_games),
            "evil_games": evil_games,
            "evil_winrate": percent(evil_wins, evil_games),
            "survival": percent(survived, total),
        }

        characters = sorted(
            [{"name": n, "plays": c["plays"], "winrate": percent(c["wins"], c["plays"])}
             for n, c in char_totals.items()],
            key=lambda c: (-c["plays"], c["name"]),
        )

        deaths = death_counts.most_common()   # [("By demon", 5), ...]

        # ---- Teammates ----
        others = conn.execute(
            "SELECT gp.game_id, p.id AS player_id, p.name, gp.end_alignment "
            "FROM game_players gp "
            "JOIN players p ON p.id = gp.player_id "
            "WHERE gp.player_id != ? AND gp.game_id IN ("
            "  SELECT game_id FROM game_players WHERE player_id = ?)",
            (player_id, player_id),
        ).fetchall()

        teammate_totals = {}      # keyed by id so the link can use it
        for o in others:
            # Only count people who ended on the same team as this player
            if o["end_alignment"] == my_alignment[o["game_id"]]:
                t = teammate_totals.setdefault(
                    o["player_id"], {"name": o["name"], "games": 0, "wins": 0}
                )
                t["games"] += 1
                t["wins"] += i_won[o["game_id"]]

        teammates = sorted(
            [{"id": pid, "name": t["name"], "games": t["games"],
              "winrate": percent(t["wins"], t["games"])}
             for pid, t in teammate_totals.items() if t["games"] >= 2],
            key=lambda t: (-t["winrate"], -t["games"]),
        )

        return render_template(
            "player.html",
            name=name,
            summary=summary,
            streaks=win_streaks(conn)[name],
            characters=characters,
            deaths=deaths,
            teammates=teammates,
            history=rows,
        )
    finally:
        conn.close()