// Strudel Drum Groove BRIDGE - Key of E Major
// Time signature: 4/4
// Feel: Sparse, tension-building, half-time vibe

setcps(135/60/4)

stack(
  // Sparse hi-hat - half-time feel
  sound(`
    [hh - - -] [hh - - -],
    [hh - - -] [hh - hh -]
  `).gain(0.5),

  // Snare on 3 only - half-time groove
  sound(`
    [- - - -] [sd - - -],
    [- - - -] [sd - - -]
  `).gain(0.85),

  // Rim clicks for texture
  sound(`
    [- rim - -] [- - rim -],
    [- rim - -] [- - - rim]
  `).gain(0.4),

  // Minimal kick - breathing room
  sound(`
    [bd - - -] [- - - -],
    [bd - - -] [- - bd -]
  `).gain(0.9),

  // Cymbal swells building tension
  sound("[- - - -] [- - - -] [- - - -] [oh - - -]")
    .gain(0.4)
    .slow(2),

  // Toms building every 4 bars
  sound("[- - - -] [- - - -] [- - - -] [- - [tom:2 tom:1] [tom:1 tom:0]]")
    .gain(0.55)
    .slow(2),

  // Subtle shaker for movement
  sound(`
    [shaker - shaker -] [shaker - shaker -],
    [shaker - shaker -] [shaker - shaker -]
  `).gain(0.2),

  // China/stack hit for drama (every 8 bars)
  sound("[cp:2 - - - - - - -]")
    .gain(0.5)
    .slow(8),

  // E bass drone for harmonic context
  note("e1")
    .s("sawtooth")
    .lpf(200)
    .gain(0.3)
    .room(0.1)
)
