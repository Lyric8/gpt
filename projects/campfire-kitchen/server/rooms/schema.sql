PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS schema_info(version INTEGER NOT NULL);
INSERT INTO schema_info SELECT 1 WHERE NOT EXISTS(SELECT 1 FROM schema_info);
CREATE TABLE IF NOT EXISTS catalogs(hash TEXT PRIMARY KEY, payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS devices(hash TEXT PRIMARY KEY, expires REAL NOT NULL);
CREATE TABLE IF NOT EXISTS rooms(
 id TEXT PRIMARY KEY, number TEXT UNIQUE NOT NULL, created REAL NOT NULL, expires REAL NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('active','archiving','archived')),
 revision INTEGER NOT NULL DEFAULT 1, catalog_hash TEXT NOT NULL REFERENCES catalogs(hash),
 settings TEXT NOT NULL, host TEXT NOT NULL, pin_salt TEXT NOT NULL, pin_hash TEXT NOT NULL,
 create_hash TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS rooms_expiry ON rooms(status,expires);
CREATE TABLE IF NOT EXISTS members(
 id TEXT PRIMARY KEY, room_id TEXT NOT NULL REFERENCES rooms(id), device_hash TEXT NOT NULL REFERENCES devices(hash),
 nickname TEXT NOT NULL, nickname_key TEXT NOT NULL, choices TEXT NOT NULL,
 UNIQUE(room_id,device_hash), UNIQUE(room_id,nickname_key)
);
CREATE INDEX IF NOT EXISTS members_room ON members(room_id);
CREATE TABLE IF NOT EXISTS operations(
 room_id TEXT NOT NULL REFERENCES rooms(id), member_id TEXT NOT NULL REFERENCES members(id) ON DELETE CASCADE,
 op_id TEXT NOT NULL, hash TEXT NOT NULL, revision INTEGER NOT NULL,
 PRIMARY KEY(room_id,member_id,op_id)
);
CREATE TABLE IF NOT EXISTS archives(
 room_id TEXT PRIMARY KEY REFERENCES rooms(id), path TEXT UNIQUE NOT NULL, payload TEXT,
 hash TEXT NOT NULL, status TEXT NOT NULL CHECK(status IN ('pending','sending','done')),
 attempts INTEGER NOT NULL DEFAULT 0, next_try REAL NOT NULL DEFAULT 0,
 lease TEXT, lease_until REAL NOT NULL DEFAULT 0, last_error TEXT,
 commit_sha TEXT, blob_sha TEXT, completed REAL
);
CREATE INDEX IF NOT EXISTS archives_due ON archives(status,next_try,lease_until);
CREATE TABLE IF NOT EXISTS service_state(name TEXT PRIMARY KEY, at REAL NOT NULL);
