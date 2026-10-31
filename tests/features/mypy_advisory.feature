Feature: Advisory mypy reporting

  Scenario: Existing type findings are reported without failing CI
    Given the Music mypy scope contains one selected source module
    And mypy reports one existing type finding
    When the advisory report is generated
    Then the report identifies the repository revision and selected scope
    And the finding remains in local output but not the CI summary