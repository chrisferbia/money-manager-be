ALTER TABLE accounts ADD COLUMN sequence INTEGER NOT NULL DEFAULT 0;

UPDATE accounts SET sequence = id;

ALTER TABLE categories ADD COLUMN sequence INTEGER NOT NULL DEFAULT 0;

UPDATE categories SET sequence = id;
