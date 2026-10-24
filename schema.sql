CREATE TABLE IF NOT EXISTS players (
    id   INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS characters (
    id   INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    type TEXT NOT NULL CHECK (type IN
        ('Townsfolk', 'Outsider', 'Minion', 'Demon', 'Traveller'))
);

CREATE TABLE IF NOT EXISTS games (
    id           INTEGER PRIMARY KEY,
    date         TEXT NOT NULL,          -- store as 'YYYY-MM-DD'
    script       TEXT,
    storyteller  TEXT,
    winning_team TEXT NOT NULL CHECK (winning_team IN ('Good', 'Evil')),

    result       TEXT,
    game_length  INTEGER,
    game_type    TEXT CHECK (game_type IN ('Discord', 'In-person'))

);

CREATE TABLE IF NOT EXISTS game_players (
    id                 INTEGER PRIMARY KEY,
    game_id            INTEGER NOT NULL REFERENCES games(id),
    player_id          INTEGER NOT NULL REFERENCES players(id),
    start_character_id INTEGER NOT NULL REFERENCES characters(id),
    start_alignment    TEXT NOT NULL CHECK (start_alignment IN ('Good', 'Evil')),
    end_character_id   INTEGER NOT NULL REFERENCES characters(id),
    end_alignment      TEXT NOT NULL CHECK (end_alignment IN ('Good', 'Evil')),
    death_cause        TEXT CHECK (death_cause IS NULL OR death_cause IN
        ('Executed', 'By demon', 'Own ability', 'Other ability', 'Survived', 'Exiled')),
    UNIQUE (game_id, player_id)          -- one row per person per game
);