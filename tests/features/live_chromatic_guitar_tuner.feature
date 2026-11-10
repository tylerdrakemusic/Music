Feature: Live chromatic guitar tuning

  Scenario: Tune clean notes across the guitar range
    Given the Windows Focusrite channel 1 monitor is active
    When sustained clean E2, A4, and E6 notes reach the input
    Then each note settles within 500 milliseconds and three cents

  Scenario: Include both five-cent boundaries in tune
    Given the Windows Focusrite channel 1 monitor is active
    When A4 is five cents flat and then five cents sharp
    Then both boundary readings report in tune

  Scenario: Tune a representative processed guitar tone
    Given the Windows Focusrite channel 1 monitor is active
    When a harmonic-rich overdrive tone with light echo reaches the input
    Then E2 settles within 500 milliseconds and five cents

  Scenario: Reject overlapping notes and resume automatically
    Given the Windows Focusrite channel 1 monitor is active
    When a valid E2 is replaced by simultaneous E2 and A2, then returns to E2
    Then overlap clears pitch and tuning resumes within 500 milliseconds

  Scenario: Clear pitch for clipping, silence, and lost callbacks
    Given the Windows Focusrite channel 1 monitor is active
    When a valid E2 is clipped, falls silent, then callbacks stop
    Then unreliable pitch clears within 500 milliseconds and the monitor stays active

  Scenario: Render the tuner in the existing monitor location
    Given the Windows Focusrite channel 1 monitor is active
    When the Trainer page is opened
    Then the compact tuner is accessible in place with responsive layout rules

  Scenario: Stop and restart without duplicating capture
    Given the Windows Focusrite channel 1 monitor is active
    When a tuned capture is started again and then stopped
    Then pitch clears and the single capture stream is released