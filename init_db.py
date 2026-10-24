import sqlite3
import csv
import os
from datetime import datetime


DB_FILE = "clocktower.db"

if os.path.exists(DB_FILE):
    os.remove(DB_FILE)
    print(f"Deleted old {DB_FILE}")

conn = sqlite3.connect(DB_FILE)
conn.execute("PRAGMA foreign_keys = ON")

with open("schema.sql", encoding="utf-8") as f:
    conn.executescript(f.read())

print("Database created.")


def ImportCharacters(conn):
    TYPE_ORDER = ["Townsfolk", "Outsider", "Minion", "Demon", "Traveller"]
    rows = []
    with open("spreadsheet_data/characters.csv", newline="", encoding="utf-8-sig") as f:
        for record in csv.DictReader(f):
            for char_type, name in record.items():
                name = (name or "").strip()
                if name:
                    rows.append((name, char_type.strip()))

    rows.sort(key=lambda r: TYPE_ORDER.index(r[1]))

    with conn:
        conn.executemany(
            "INSERT INTO characters (name, type) VALUES (?, ?) "
            "ON CONFLICT(name) DO UPDATE SET type = excluded.type",
            rows,
        )
    print(f"Imported {len(rows)} characters.")


# Which team wins for each result type
WINNER = {
    "Executed demon": "Good",
    "Slayer win":     "Good",
    "Mayor win":      "Good",
    "Demon suicide":  "Good",
    "Destroyed town": "Evil",
}


def ImportGames(conn):
    char_ids = {name: cid for cid, name in
                conn.execute("SELECT id, name FROM characters")}
    winning = {}   # game id -> 'Good' / 'Evil'

    with conn:
        # ---- games ----
        with open("spreadsheet_data/games.tsv", newline="", encoding="utf-8-sig") as f:
            for row in csv.reader(f, delimiter="\t"):
                if not row or not row[0].strip():
                    continue
                gid, script, teller, result, length, d, gtype = [c.strip() for c in row]
                gid = int(gid)

                if result not in WINNER:
                    raise SystemExit(f"Game {gid}: unknown result '{result}'")
                winning[gid] = WINNER[result]

                iso_date = datetime.strptime(d, "%d/%m/%Y").date().isoformat()

                conn.execute(
                    "INSERT INTO games "
                    "(id, date, script, storyteller, winning_team, result, game_length, game_type) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (gid, iso_date, script or None, teller or None,
                     winning[gid], result, float(length), gtype),
                )

        # ---- players in games ----
        with open("spreadsheet_data/game_players.tsv", newline="", encoding="utf-8-sig") as f:
            for row in csv.reader(f, delimiter="\t"):
                if not row or not row[0].strip():
                    continue
                gid, name, start_a, end_a, start_c, end_c, outcome, death = [c.strip() for c in row]
                gid = int(gid)

                for c in (start_c, end_c):
                    if c not in char_ids:
                        raise SystemExit(f"Game {gid}, {name}: unknown character '{c}'")

                # Sanity check against the Win/Lose column in your sheet
                if (end_a == winning[gid]) != (outcome == "Win"):
                    print(f"Warning: game {gid}, {name}: sheet says {outcome}, "
                          f"but {end_a} side vs {winning[gid]} win disagrees")

                conn.execute("INSERT OR IGNORE INTO players (name) VALUES (?)", (name,))
                player_id = conn.execute(
                    "SELECT id FROM players WHERE name = ?", (name,)
                ).fetchone()[0]

                conn.execute(
                    "INSERT INTO game_players "
                    "(game_id, player_id, start_character_id, start_alignment, "
                    " end_character_id, end_alignment, death_cause) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (gid, player_id, char_ids[start_c], start_a,
                     char_ids[end_c], end_a,
                     None if death == "Survived" else death),
                )

    print("Games imported.")


ImportCharacters(conn)
ImportGames(conn)

conn.close()