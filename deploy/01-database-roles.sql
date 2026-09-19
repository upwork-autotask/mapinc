-- Phase 1.1 — least-privilege database roles.
-- Run as the postgres superuser:  psql -U postgres -h localhost -d mapinc -f 01-database-roles.sql
-- Replace the three passwords first (long random strings).

\set ON_ERROR_STOP on

CREATE ROLE mapinc_owner  LOGIN PASSWORD 'CHANGE-ME-owner';    -- owns the schema; used ONLY for manage.py migrate
CREATE ROLE mapinc_app    LOGIN PASSWORD 'CHANGE-ME-app';      -- what run.bat uses
CREATE ROLE mapinc_report LOGIN PASSWORD 'CHANGE-ME-report';   -- optional read-only reporting

ALTER DATABASE mapinc OWNER TO mapinc_owner;
REVOKE ALL ON DATABASE mapinc FROM PUBLIC;
GRANT CONNECT ON DATABASE mapinc TO mapinc_app, mapinc_report;

-- Hand existing objects (created during setup by the dev role) to the owner role.
REASSIGN OWNED BY mapinc TO mapinc_owner;

GRANT USAGE ON SCHEMA public TO mapinc_app, mapinc_report;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT CREATE ON SCHEMA public TO mapinc_owner;

GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO mapinc_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO mapinc_app;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO mapinc_report;

-- The audit trail is insert-only for the application.
REVOKE UPDATE, DELETE, TRUNCATE ON letters_auditevent FROM mapinc_app;

-- Tables created by future migrations (run as mapinc_owner) get the same grants automatically.
ALTER DEFAULT PRIVILEGES FOR ROLE mapinc_owner IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO mapinc_app;
ALTER DEFAULT PRIVILEGES FOR ROLE mapinc_owner IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO mapinc_app;
ALTER DEFAULT PRIVILEGES FOR ROLE mapinc_owner IN SCHEMA public
    GRANT SELECT ON TABLES TO mapinc_report;

-- Retire the development role and rotate the superuser password.
DROP ROLE IF EXISTS mapinc;
ALTER ROLE postgres PASSWORD 'CHANGE-ME-postgres';

-- Verify: every mapinc role must show f f
SELECT rolname, rolsuper, rolcreatedb, rolcreaterole FROM pg_roles WHERE rolname LIKE 'mapinc%';
