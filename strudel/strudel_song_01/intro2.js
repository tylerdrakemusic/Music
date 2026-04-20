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
  `).gain("<0.2>")  // Gradual volume build
    .slow(1),  // 8 bars total (pattern repeats 2x)
  
  // Bass line - Ab Major progression: Amaj7 (4 beats) → C (1.5 beats) → D (2.5 beats)
  // Try different bass sounds: bass, bass0, bass1, bass2, bass3, casio, gm_acoustic_bass, gm_electric_bass_finger, gm_electric_bass_pick, gm_fretless_bass, gm_slap_bass_1, gm_slap_bass_2, gm_synth_bass_1, gm_synth_bass_2
  note(`
  [ab1 ~  ~ ~ ] [~  g2  ab2 ~ ] [c2  ~ c1 d1] [~  ~  f1  fs1],
  [ab1 ~  ~ ~ ] [~  g2  ab2 ~ ] [c2  ~ c1 d1] [~  ~  f1  fs1],
  [ab1 ~  ~ ~ ] [~  g2  ab2 ~ ] [c2  ~ c1 d1] [~  ~  f1  fs1],
  [ab1 ~  ~ ~ ] [~  g2  ab2 ~ ] [c2  ~ c1 d1] [~  ~  f1  fs1]
  `).s("<gm_acoustic_bass>")  // Cycles through bass sounds
    .sustain(2)  // Hold notes longer instead of cutting at beat
    .lpf("<400 600 800 1000>")  // Filter opens up
    .gain("<0.4>")  // Fades in from bar 3
    .room(0.3)
    .slow(2),  // 8 bars total
  
  // Hi-hat variation enters bar 5 for extra energy
  sound("hh*8")
    .gain("<0.6>")  // Enters bar 5
    .pan(sine.slow(8))  // Slow stereo movement
    .slow(1),  // 8 bars
  
  // Shaker - adds texture throughout
  // Cycles through all 16 small shaker samples
  sound("shaker_small*16")
    .n("<0 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15>")  // Test all 16 shaker_small samples
    .gain("<0 0.15 0.2 0.25>")  // Gradual fade in
    .pan(perlin.slow(4))  // Subtle stereo movement
    .slow(1),  // 8 bars
  
  // Piano - enters on third pass through (bar 5)
  // Plays the chord progression: Ab → C → D
  // Cycles through different voicings/inversions for each chord
  note(`
  [<ab3, c4, eb4> ~ ~ ~] [~ ~ ~ ~] [<c3, eb3, ab3> <eb3, ab3, c4> ~ ~ <d3, fs3, a3>] [~ ~ ~ ~]
  `).s("piano")
    .velocity(0.3)
    .sustain(2)
    .room(0.3)
    .gain("<0.3>")  // Silent first 2 passes, enters on 3rd pass (bar 5)
    .slow(2)  // 8 bars total
    // Voicing options to try (replace the note pattern above):
    // Root position: [<ab3, c4, eb4> ~ ~ ~] [~ ~ ~ ~] [<c3, e3, g3> ~ ~ <d3, fs3, a3>] [~ ~ ~ ~]
    // First inversion: [<c3, eb3, ab3> ~ ~ ~] [~ ~ ~ ~] [<e3, g3, c4> ~ ~ <fs3, a3, d4>] [~ ~ ~ ~]
    // Second inversion: [<eb3, ab3, c4> ~ ~ ~] [~ ~ ~ ~] [<g3, c4, e4> ~ ~ <a3, d4, fs4>] [~ ~ ~ ~]
    // Higher octave: [<ab4, c5, eb5> ~ ~ ~] [~ ~ ~ ~] [<c4, e4, g4> ~ ~ <d4, fs4, a4>] [~ ~ ~ ~]
    // Mixed voicings: [<c4, eb4, ab4> ~ ~ ~] [~ ~ ~ ~] [<e3, g3, c4> ~ ~ <fs3, a3, d4>] [~ ~ ~ ~]
    // Spread voicing: [<ab2, c4, eb4> ~ ~ ~] [~ ~ ~ ~] [<c3, e4, g4> ~ ~ <d3, fs4, a4>] [~ ~ ~ ~]
    ,
  
  // Melodic sample - enters with piano on third pass (bar 5)
  // Plays chord progression: Ab → C → D
  // 16th notes play different inversions/voicings of same chord
  note("[<ab3, c4, eb4> <c3, eb3, g3, ab3> ~ [<c3, eb3, ab3> <eb3, ab3, c4>]] [~ [<ab3, c4, eb4><ab3, c4, eb4>] ~ [<eb4, ab4, c5><eb4, ab4, c5>]] [<c3, e3, g3> ~ [<e3, g3, c4><g3, c4, e4>] <d3, fs3, a3>] [~ ~ ~ ~]")
  .room(0.5)
  .size(0.9)
  .s("<wt_oboe>")
  .gain("<1.5>")
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