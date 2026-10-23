import sqlite3
import csv

conn = sqlite3.connect("clocktower.db")
with open("schema.sql") as f:
    conn.executescript(f.read())
conn.close()
print("Database created.")




conn = sqlite3.connect("clocktower.db")
conn.execute("PRAGMA foreign_keys = ON")


TYPE_ORDER = ["Townsfolk", "Outsider", "Minion", "Demon", "Traveller"]
rows = []
with open("characters.csv", newline="", encoding="utf-8-sig") as f:
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

# Add a player
conn.execute("INSERT OR IGNORE INTO players (name) VALUES (?)", ("Alice",))
conn.execute("INSERT OR IGNORE INTO players (name) VALUES (?)", ("Bob",))
conn.execute("INSERT OR IGNORE INTO players (name) VALUES (?)", ("Charlie",))
conn.execute("INSERT OR IGNORE INTO players (name) VALUES (?)", ("Donald",))
conn.execute("INSERT OR IGNORE INTO players (name) VALUES (?)", ("Eric",))

# Add a game, and get its new id back
cur = conn.execute(
    "INSERT INTO games (date, script, storyteller, winning_team) VALUES (?, ?, ?, ?)",
    ("2026-10-18", "Trouble Brewing", "Carol", "Good"),
)
game_id = cur.lastrowid

# Add a player's row for that game, looking up ids by name
conn.execute(
    """
    INSERT INTO game_players
        (game_id, player_id, start_character_id, start_alignment,
         end_character_id, end_alignment, death_cause)
    VALUES (
        ?,
        (SELECT id FROM players WHERE name = ?),
        (SELECT id FROM characters WHERE name = ?), ?,
        (SELECT id FROM characters WHERE name = ?), ?,
        ?
    )
    """,
    (game_id, "Alice", "Empath", "Good", "Empath", "Good", None),
)



print(f"Imported {len(rows)} characters.")

conn.commit()   # nothing is saved until you do this
conn.close()