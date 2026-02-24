-- Gold: available (unrostered) players per league
-- Business-level aggregate for API /players/available
SELECT
  p.player_id AS id,
  p.player_id,
  p.name,
  p.position,
  p.team,
  p.status,
  p.age,
  p.trending
FROM silver_players p
LEFT JOIN silver_rosters r ON r.league_id = :league_id AND p.player_id IN (SELECT unnest(r.players))
WHERE r.roster_id IS NULL;
