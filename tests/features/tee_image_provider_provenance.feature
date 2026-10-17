Feature: Tee candidate provider provenance

  Scenario: Pending and approved candidates preserve the actual provider route
    Given an approved tee concept and a provider response with limited metadata
    When its image is staged and explicitly approved
    Then pending results and the approved sidecar preserve provenance and mark unavailable metadata unverified

  Scenario: Music selects the Workspace tee authorization cascade
    Given Workspace exports distinct generic and tee cascade factories
    When Music resolves its default tee cascade
    Then it selects the tee factory and never calls the generic factory