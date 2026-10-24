import sqlite3
from datetime import date
from flask import Flask, render_template, request, redirect, url_for, flash, abort

app = Flask(__name__)
app.secret_key = "dev-only-change-later"   # needed for flash messages

# Keep this in sync with the CHECK list in schema.sql
DEATH_CAUSES = ["Executed", "By demon", "Own ability", "Other ability", "Survived", "Exiled"]


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


@app.route("/", methods=["GET", "POST"])
def stat_page():
    conn = get_db()
    try:
        headline = conn.execute(
            "SELECT (SELECT COUNT(*) FROM games) AS games, "
            "       (SELECT COUNT(*) FROM players) AS players, "
            "       (SELECT COUNT(DISTINCT storyteller) FROM games) AS storytellers, "
            "       (SELECT ROUND(100.0 * SUM(winning_team = 'Evil') / COUNT(*), 1) "
            "        FROM games) AS evil_winrate"
        ).fetchone()

        player_stats = conn.execute(
            "SELECT p.name, COUNT(*) AS games, "
            "  SUM(gp.end_alignment = g.winning_team) AS wins, "
            "  ROUND(100.0 * SUM(gp.end_alignment = g.winning_team) / COUNT(*), 1) AS winrate "
            "FROM game_players gp "
            "JOIN players p ON p.id = gp.player_id "
            "JOIN games g   ON g.id = gp.game_id "
            "GROUP BY p.id HAVING games >= 1 "
            "ORDER BY games DESC, winrate DESC"
        ).fetchall()

        character_rows = conn.execute(
            "SELECT c.type, c.name, COUNT(*) AS plays, "
            "  ROUND(100.0 * SUM(gp.end_alignment = g.winning_team) / COUNT(*), 1) AS winrate "
            "FROM game_players gp "
            "JOIN characters c ON c.id = gp.start_character_id "
            "JOIN games g      ON g.id = gp.game_id "
            "GROUP BY c.id ORDER BY plays DESC, c.name"
        ).fetchall()

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