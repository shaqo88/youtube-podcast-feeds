import sqlite3
import unittest
from pathlib import Path


class AccountBackupTest(unittest.TestCase):
    def test_sql_export_restore_preserves_cursors_receipts_and_deletion_jobs(self):
        source = sqlite3.connect(':memory:')
        source.executescript(Path('workers/accounts/migrations/0001_accounts.sql').read_text())
        source.execute("INSERT INTO accounts(uid,uid_hash,created_at) VALUES('alice','hash',1)")
        source.execute("INSERT INTO operations(uid,operation_id,fingerprint,kind,item_id,expected_revision,value,deleted,updated_at) VALUES('alice','one','digest','follows','example',0,'{}',1,2)")
        source.execute("INSERT INTO deletion_jobs(uid,attempts,next_attempt) VALUES('alice',2,100)")
        source.execute("UPDATE accounts SET state='deleting' WHERE uid='alice'")
        source.execute("INSERT INTO deleted_accounts VALUES('hash')")
        source.commit()
        snapshot = '\n'.join(source.iterdump())
        restored = sqlite3.connect(':memory:')
        restored.executescript(snapshot)
        for table in ('accounts', 'library', 'changes', 'operations', 'deletion_jobs', 'deleted_accounts'):
            self.assertEqual(source.execute('SELECT * FROM ' + table).fetchall(), restored.execute('SELECT * FROM ' + table).fetchall())
        with self.assertRaisesRegex(sqlite3.IntegrityError, 'account_blocked'):
            restored.execute("INSERT INTO accounts(uid,uid_hash,created_at) VALUES('replayed','hash',3)")
        with self.assertRaisesRegex(sqlite3.IntegrityError, 'account_blocked'):
            restored.execute("INSERT INTO operations(uid,operation_id,fingerprint,kind,item_id,expected_revision,value,deleted,updated_at) VALUES('alice','two','digest2','follows','example',1,'{}',0,3)")
