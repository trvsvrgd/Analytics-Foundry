-- Bronze: raw NFL Sleeper players (source-specific; append-only)
-- Unity Catalog–friendly: catalog.schema.table
-- Example: CREATE TABLE IF NOT EXISTS bronze.nfl_sleeper.players (...)
SELECT
  player_id,
  display_name,
  position,
  team,
  status,
  injury_status,
  age,
  number,
  raw
FROM bronze_nfl_sleeper_players;
