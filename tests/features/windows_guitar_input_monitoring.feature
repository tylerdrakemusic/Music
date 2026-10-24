Feature: Windows Guitar Trainer input monitoring

  Scenario: Start monitoring the Scarlett input
    Given the Trainer is running on Windows, the Scarlett is available, and guitar signal reaches channel 1
    When the user starts monitoring
    Then the level meter responds to the input and the UI reports signal present

  Scenario: Report no signal below the threshold
    Given monitoring is active
    When the input falls below the signal-present threshold
    Then the UI reports no signal.

  Scenario: Warn when the input clips
    Given monitoring is active
    When the input reaches the clipping threshold
    Then the UI displays a clipping/overload warning.

  Scenario: Report an unavailable Scarlett input
    Given the Scarlett or its input is unavailable
    When the user starts monitoring
    Then the UI reports the capture error and does not indicate that monitoring is active.

  Scenario: Stop capture and release the device
    Given monitoring is active
    When the user stops monitoring or the Trainer shuts down
    Then capture stops, the device is released, and meter updates cease.