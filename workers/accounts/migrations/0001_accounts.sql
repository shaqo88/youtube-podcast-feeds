PRAGMA foreign_keys = ON;
CREATE TABLE accounts (
  uid TEXT PRIMARY KEY,
  uid_hash TEXT NOT NULL,
  display_name TEXT NOT NULL DEFAULT '',
  state TEXT NOT NULL DEFAULT 'active' CHECK(state IN ('active','deleting')),
  created_at INTEGER NOT NULL
);
-- A one-way receipt blocks replay of previously verified tokens across Worker
-- isolates after personal data and Firebase identity have been removed.
CREATE TABLE deleted_accounts (uid_hash TEXT PRIMARY KEY);
CREATE TRIGGER prevent_deleted_account BEFORE INSERT ON accounts BEGIN
  SELECT (CASE WHEN EXISTS(SELECT 1 FROM deleted_accounts WHERE uid_hash=NEW.uid_hash)
    THEN RAISE(ABORT,'account_blocked') END);
END;
CREATE TABLE library (
  uid TEXT NOT NULL REFERENCES accounts(uid) ON DELETE CASCADE,
  kind TEXT NOT NULL CHECK(kind IN ('follows','saved','progress')),
  item_id TEXT NOT NULL,
  value TEXT NOT NULL CHECK(json_valid(value)),
  deleted INTEGER NOT NULL DEFAULT 0 CHECK(deleted IN (0,1)),
  revision INTEGER NOT NULL,
  updated_at INTEGER NOT NULL,
  PRIMARY KEY(uid,kind,item_id)
);
CREATE TABLE changes (
  sequence INTEGER PRIMARY KEY AUTOINCREMENT,
  uid TEXT NOT NULL REFERENCES accounts(uid) ON DELETE CASCADE,
  kind TEXT NOT NULL,
  item_id TEXT NOT NULL,
  value TEXT NOT NULL,
  deleted INTEGER NOT NULL,
  revision INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
);
CREATE INDEX changes_by_owner ON changes(uid,sequence);
CREATE TABLE operations (
  uid TEXT NOT NULL REFERENCES accounts(uid) ON DELETE CASCADE,
  operation_id TEXT NOT NULL,
  fingerprint TEXT NOT NULL,
  kind TEXT NOT NULL,
  item_id TEXT NOT NULL,
  expected_revision INTEGER NOT NULL,
  value TEXT NOT NULL CHECK(json_valid(value)),
  deleted INTEGER NOT NULL,
  updated_at INTEGER NOT NULL,
  result TEXT,
  PRIMARY KEY(uid,operation_id)
);
-- A single insert applies CAS, state, change cursor and the retry receipt in
-- one SQLite transaction. The same operation cannot succeed with two payloads.
CREATE TRIGGER apply_operation AFTER INSERT ON operations BEGIN
  SELECT (CASE WHEN (SELECT state FROM accounts WHERE uid=NEW.uid) != 'active'
    THEN RAISE(ABORT,'account_blocked') END);
  SELECT (CASE WHEN COALESCE((SELECT revision FROM library
    WHERE uid=NEW.uid AND kind=NEW.kind AND item_id=NEW.item_id),0) != NEW.expected_revision
    THEN RAISE(ABORT,'revision_conflict') END);
  INSERT INTO library(uid,kind,item_id,value,deleted,revision,updated_at)
    VALUES(NEW.uid,NEW.kind,NEW.item_id,NEW.value,NEW.deleted,NEW.expected_revision+1,NEW.updated_at)
    ON CONFLICT(uid,kind,item_id) DO UPDATE SET value=excluded.value,deleted=excluded.deleted,
      revision=excluded.revision,updated_at=excluded.updated_at;
  INSERT INTO changes(uid,kind,item_id,value,deleted,revision,updated_at)
    SELECT uid,kind,item_id,value,deleted,revision,updated_at FROM library
    WHERE uid=NEW.uid AND kind=NEW.kind AND item_id=NEW.item_id;
  UPDATE operations SET result=json_object('kind',NEW.kind,'id',NEW.item_id,
    'value',json(NEW.value),'deleted',NEW.deleted,'revision',NEW.expected_revision+1,'updatedAt',NEW.updated_at)
    WHERE uid=NEW.uid AND operation_id=NEW.operation_id;
END;
CREATE TABLE imports (
  uid TEXT NOT NULL REFERENCES accounts(uid) ON DELETE CASCADE,
  import_id TEXT NOT NULL,
  fingerprint TEXT NOT NULL,
  result TEXT NOT NULL,
  PRIMARY KEY(uid,import_id)
);
CREATE TABLE deletion_jobs (
  uid TEXT PRIMARY KEY REFERENCES accounts(uid) ON DELETE CASCADE,
  attempts INTEGER NOT NULL DEFAULT 0,
  next_attempt INTEGER NOT NULL,
  lease_until INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE publisher_requests (
  request_id TEXT PRIMARY KEY,
  uid TEXT NOT NULL REFERENCES accounts(uid) ON DELETE CASCADE,
  operation_id TEXT NOT NULL,
  fingerprint TEXT NOT NULL,
  kind TEXT NOT NULL CHECK(kind IN ('submission','claim')),
  show_slug TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'submitted',
  revision INTEGER NOT NULL DEFAULT 0,
  delivery TEXT NOT NULL DEFAULT 'reserved' CHECK(delivery IN ('reserved','uncertain','delivered')),
  lease_until INTEGER NOT NULL DEFAULT 0,
  challenge TEXT NOT NULL DEFAULT '',
  created_at INTEGER NOT NULL,
  UNIQUE(uid,operation_id)
);
CREATE INDEX publisher_by_owner ON publisher_requests(uid,created_at,request_id);
CREATE TABLE publisher_events (
  event_id TEXT PRIMARY KEY,
  request_id TEXT NOT NULL REFERENCES publisher_requests(request_id) ON DELETE CASCADE,
  fingerprint TEXT NOT NULL,
  expected_revision INTEGER NOT NULL
);
CREATE TRIGGER publisher_event_cas BEFORE INSERT ON publisher_events BEGIN
  SELECT (CASE WHEN (SELECT revision FROM publisher_requests WHERE request_id=NEW.request_id) != NEW.expected_revision
    THEN RAISE(ABORT,'status_conflict') END);
  SELECT (CASE WHEN NOT EXISTS(SELECT 1 FROM publisher_requests r JOIN accounts a ON a.uid=r.uid
    WHERE r.request_id=NEW.request_id AND a.state='active') THEN RAISE(ABORT,'account_blocked') END);
END;
CREATE TRIGGER publisher_request_owner BEFORE INSERT ON publisher_requests BEGIN
  SELECT (CASE WHEN (SELECT state FROM accounts WHERE uid=NEW.uid) != 'active' THEN RAISE(ABORT,'account_blocked') END);
END;
CREATE TABLE publisher_shows (
  uid TEXT NOT NULL REFERENCES accounts(uid) ON DELETE CASCADE,
  show_slug TEXT NOT NULL,
  request_id TEXT NOT NULL REFERENCES publisher_requests(request_id) ON DELETE CASCADE,
  PRIMARY KEY(uid,show_slug)
);
