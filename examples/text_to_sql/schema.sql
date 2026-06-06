-- Tiny self-contained schema + seed rows for the text-to-SQL eval (in-memory SQLite).
CREATE TABLE employees (
    id     INTEGER PRIMARY KEY,
    name   TEXT NOT NULL,
    dept   TEXT NOT NULL,
    salary INTEGER NOT NULL
);

INSERT INTO employees (id, name, dept, salary) VALUES
    (1, 'Ada',   'engineering', 120000),
    (2, 'Ben',   'engineering',  95000),
    (3, 'Cara',  'sales',        80000),
    (4, 'Dan',   'sales',        72000),
    (5, 'Erin',  'marketing',   105000);
