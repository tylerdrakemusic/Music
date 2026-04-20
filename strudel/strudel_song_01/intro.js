// Strudel Song 01: 133 BPM, Key of Ab Major
// Progression: Amaj7 (4 beats) → C (1.5 beats) → D (2.5 beats)
// Structure: Intro (8 bars) → Build
// Time signature: 4/4
samples('bubo:waveforms');
setcps(133/60/4)

// ============================================
// INTRO - 8 bars: Drums + Bass Build
// ============================================

stack(
  // Drum pattern - starts simple, builds over 8 bars
  sound(`
  [hh -  hh - ] [hh -  hh - ] [hh -  hh - ] [hh -  hh - ],
  [-  -  -  - ] [sd -  -  - ] [-  -  -  - ] [sd -  -  - ],
  [bd -  -  - ] [-  -  -  - ] [bd - bd  - ] [-  -  -  - ]
  `).gain("<0.1 0.1 0.2 0.2>")  // Gradual volume build
    .slow(1),  // 8 bars total (pattern repeats 2x)
  
  // Bass line - Ab Major progression: Amaj7 (4 beats) → C (1.5 beats) → D (2.5 beats)
  // Try different bass sounds: "square", "triangle", "sine", "bass", "bass1", "bass2", "bass3"
  note(`
  [ab1 ~  ~ ~ ] [~  g2  ab2 ~ ] [c2  ~ bb1 d2] [~  ~  f2  fs2],
  [ab1 ~  ~ ~ ] [~  g2  ab2 ~ ] [c2  ~ bb1 d2] [~  ~  f2  fs2],
  [ab1 ~  ~ ~ ] [~  g2  ab2 ~ ] [c2  ~ bb1 d2] [~  ~  f2  fs2],
  [ab1 ~  ~ ~ ] [~  g2  ab2 ~ ] [c2  ~ bb1 d2] [~  ~  f2  fs2]
  `).s("<sine>")  // Cycles through bass sounds
    .sustain(2)  // Hold notes longer instead of cutting at beat
    .lpf("<400 600 800 1000>")  // Filter opens up
    .gain("<.05 .1 0.2 0.3>")  // Fades in from bar 3
    .room(0.3)
    .slow(2),  // 8 bars total
  
  // Hi-hat variation enters bar 5 for extra energy
  sound("hh*8")
    .gain("<0 0 0 0 0.3 0.4 0.5 0.6>")  // Enters bar 5
    .pan(sine.slow(8))  // Slow stereo movement
    .slow(1),  // 8 bars
  
  // Piano - enters on third pass through (bar 5)
  // Plays the chord progression: Ab → C → D
  note(`
  [<ab3, c4, eb4> ~ ~ ~] [~ ~ ~ ~] [<c3, e3, g3> ~ ~ <d3, fs3, a3>] [~ ~ ~ ~]
  `).s("piano")
    .velocity(0.3)
    .sustain(2)
    .room(0.3)
    .gain("<0 0 0.1 0.3>")  // Silent first 2 passes, enters on 3rd pass (bar 5)
    .slow(2),  // 8 bars total
  
  // Flute sample - enters with piano on third pass (bar 5)
  // Plays chord progression: Ab → C → D

  note("[<ab3, c4, eb4> <c3, eb3, g3, ab3> ~ <c3, eb3, g3, ab3>] [~ <ab3, c4, eb4> ~ <ab3, c4, eb4>] [<c3, e3, g3> ~ <g3, c4, e4> <d3, fs3, a3>] [~ ~ ~ ~]")
  .room(0.5)
  .size(0.9)
  .s("wt_flute")
  .gain("<.05 .3 0.4 0.5>")
  .velocity(0.25)
  .often(n => n.ply(1))
  .release(0.125)
  .decay("<0.05 0.25 0.3 0.4>")
  .sustain(3)
  .cutoff(2000)
  .cutoff("<1000 2000 4000>").slow(2)
._scope()
)

// ============================================
// Next: Add verse section below
// ============================================