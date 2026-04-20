// Strudel Drum Groove CHORUS - Key of E Major
// Time signature: 4/4
// Feel: Big, open, anthemic chorus energy

setcps(135/60/4)

stack(
  // Open hi-hats - quarter notes for bigger feel
  sound(`
    [oh - oh -] [oh - oh -],
    [oh - oh -] [oh - oh oh]
  `).gain(0.55),

  // Crash accents on downbeats
  sound(`
    [cp - - -] [- - - -],
    [cp - - -] [- - - -]
  `).gain(0.6),

  // Snare - harder backbeat with fills
  sound(`
    [- - sd -] [- - sd -],
    [- - sd -] [- - sd sd]
  `).gain(1.0),

  // Snare flam/layering for thickness
  sound(`
    [- - sn:1 -] [- - sn:1 -],
    [- - sn:1 -] [- - sn:1 -]
  `).gain(0.3),

  // Kick drum - four on the floor drive
  sound(`
    [bd - bd -] [bd - bd -],
    [bd - bd -] [bd bd bd -]
  `).gain(1.0),

  // Ride bell for brightness
  sound(`
    [- ride:1 - ride:1] [- ride:1 - ride:1],
    [- ride:1 - ride:1] [- ride:1 - -]
  `).gain(0.35),

  // Floor tom pulse for power
  sound(`
    [tom:0 - - -] [- - - -],
    [tom:0 - - -] [- - - -]
  `).gain(0.4),

  // Crash hit every 4 bars for section markers
  sound("[cp:1 - - - - - - -]")
    .gain(0.7)
    .slow(4),

  // E bass drone for harmonic context
  note("e1")
    .s("sawtooth")
    .lpf(200)
    .gain(0.3)
    .room(0.1)
)
