CREATE USER google_indexer with password 'google_indexer_pwd' createdb superuser;
CREATE DATABASE google_indexer_backend;
GRANT ALL PRIVILEGES ON DATABASE google_indexer_backend TO google_indexer;
-- create extension postgis;