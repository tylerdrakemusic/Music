// Strudel Drum Groove - Key of Emajor
// Time signature: 4/4
// Feel: Driving rock/indie groove

setcps(135/60/4)

stack(
  // Hi-hats - steady 8th notes with open hat accents
  sound(`
    [hh hh hh hh hh hh hh hh],
    [hh hh hh hh hh hh oh hh]
  `).gain("[0.6 0.4 0.5 0.4 0.6 0.4 0.5 0.4]"),

  // Snare - backbeat on 2 and 4 with ghost notes
  sound(`
    [- - - - sd - - -],
    [- - - - sd - - -]
  `).gain(0.9),

  // Ghost snares for groove
  sound(`
    [- sn:3 - - - sn:3 - sn:3],
    [- sn:3 - sn:3 - - sn:3 -]
  `).gain(0.25),

  // Kick drum pattern - punchy and driving
  sound(`
    [bd - - bd - - bd -],
    [bd - bd - - bd - -]
  `).gain(0.95),

  // Ride cymbal - adds texture every other bar
  sound(`
    [- - - - - - - -],
    [ride - - - ride - - -]
  `).gain(0.4),

  // Crash on downbeat of phrase
  sound("[cp - - - - - - -]")
    .gain(0.5)
    .slow(4),

  // Low tom fill every 4 bars
  sound("[- - - - - - [tom:2 tom:2] [tom:1 tom:0]]")
    .gain(0.6)
    .slow(4),

  // Em bass drone for harmonic context
  note("e1")
    .s("sawtooth")
    .lpf(200)
    .gain(0.3)
    .room(0.1)
)
