-- Silver: cleaned/conformed players (canonical entity)
-- Dedup, normalize; Unity Catalog–friendly
SELECT
  player_id,
  COALESCE(display_name, name, '') AS name,
  COALESCE(position, '') AS position,
  COALESCE(team, '') AS team,
  COALESCE(status, '') AS status,
  COALESCE(injury_status, '') AS injury_status,
  CAST(age AS INT) AS age,
  CAST(trending AS DOUBLE) AS trending,
  updated_at
FROM bronze_nfl_sleeper_players
WHERE player_id IS NOT NULL;
