Feature: Polarity-aware tee artwork derivatives

  Scenario: Authorized candidate prompts alternate edge polarity
    Given an approved tee concept with authorization for one through four candidates
    When candidate prompts are assembled for each authorized count
    Then the prompts alternate lighter keys on dark blanks and darker keys on light blanks

  Scenario: Only explicitly approved authorized candidates get derivatives
    Given chat and batch flows authorize two individually decided candidates
    When one candidate is approved and one is rejected through each flow
    Then only approved candidates get derivatives and unauthorized candidates are rejected

  Scenario: A confident approved PNG creates a configured transparent derivative
    Given a synthetic PNG whose perimeter key meets the confidence rule
    When exact-image approval triggers post-approval conversion
    Then the opaque source is unchanged and a configured RGBA derivative and sidecar are saved

  Scenario: Ambiguous perimeter colors preserve approval and source
    Given a synthetic PNG with ambiguous perimeter colors
    When exact-image approval triggers an attempted conversion
    Then approval and source remain intact, no derivative is created, and failure is reported

  Scenario: Conversion failure removes partial output without revoking approval
    Given an approved PNG and a conversion process that fails after partial output
    When the chat-mediated exact-image decision approves the candidate
    Then approval and source remain intact, partial output is removed, and failure is reported