import sqlite3

conn = sqlite3.connect("clocktower.db")
with open("schema.sql") as f:
    conn.executescript(f.read())
conn.close()
print("Database created.")


conn = sqlite3.connect("clocktower.db")
conn.execute("PRAGMA foreign_keys = ON")

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

conn.commit()   # nothing is saved until you do this
conn.close()