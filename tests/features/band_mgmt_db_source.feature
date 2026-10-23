Feature: Band management generation uses heartmusic.db

  Scenario: DB source wins over stale JSON exports while preserving BM_INLINE behavior
    Given an isolated heartmusic database contains the band catalog arrangement and active setlist
    And legacy JSON exports contain stale band and catalog values
    When band management output is generated
    Then the existing BM_INLINE shape is populated from the database
    And the band selector catalog active setlist BPM sheet music and audio behavior are preserved
    And the footer identifies heartmusic.db as its source

  Scenario Outline: Database failures never fall back to legacy JSON exports
    Given legacy JSON exports contain a recognizable fallback value
    And the database <failure> occurs
    When band management output is generated
    Then generation fails clearly with a database error
    And the legacy JSON value is never returned

    Examples:
      | failure |
      | open    |
      | query   |

  Scenario: Explicit HEARTMUSIC_DB_PATH takes precedence over worktree discovery
    Given an explicit heartmusic database path is configured
    When the worktree database path is resolved
    Then the configured database path remains selected
