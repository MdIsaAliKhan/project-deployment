-- Run this once against your existing database if you see:
-- "dict object has no attribute tab_switches"
-- It safely adds the column only if it doesn't already exist.

USE online_exam;

ALTER TABLE results
  ADD COLUMN IF NOT EXISTS tab_switches INT NOT NULL DEFAULT 0;
