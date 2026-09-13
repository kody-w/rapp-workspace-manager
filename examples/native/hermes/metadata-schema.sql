-- Synthetic gate fixture, not a claim about every installed Hermes schema.
PRAGMA user_version = 0;
CREATE TABLE projects (id TEXT PRIMARY KEY, path TEXT);
CREATE TABLE folders (id TEXT PRIMARY KEY, project_id TEXT, path TEXT);
CREATE TABLE sessions (
    id TEXT PRIMARY KEY,
    project_id TEXT,
    folder_id TEXT,
    cwd TEXT,
    created_at REAL,
    updated_at REAL
);
INSERT INTO projects VALUES ('example-project', '/home/example/work/project-01');
INSERT INTO folders VALUES ('example-folder-a', 'example-project', '/home/example/work/folder-a');
INSERT INTO folders VALUES ('example-folder-b', 'example-project', '/home/example/work/folder-b');
INSERT INTO sessions VALUES ('example-session', 'example-project', 'example-folder-a', NULL, 1767225600, 1767225900);
