// Strudel groove: 133 BPM, Key of Em
// Progression: Em, G, Bm, Cadd9 (4 beats per chord)
// Time signature: 4/4

setcps(133/60/4)

stack(
  // Drum pattern with grid structure
  sound(`
  [hh hh hh hh] [hh hh hh hh] [hh hh hh hh] [hh hh hh hh],
  [-  -  -  - ] [sd -  -  - ] [-  -  -  - ] [sd -  -  - ],
  [bd -  bd - ] [-  -  bd - ] [bd -  bd - ] [-  -  bd - ]
  `).gain(0.8),
  
  // Bass line - root notes holding for 4 beats each
  note(`
  [e2 -  -  - ] [-  -  -  - ] [-  -  -  - ] [-  -  -  - ],
  [-  -  -  - ] [g2 -  -  - ] [-  -  -  - ] [-  -  -  - ],
  [-  -  -  - ] [-  -  -  - ] [b2 -  -  - ] [-  -  -  - ],
  [-  -  -  - ] [-  -  -  - ] [-  -  -  - ] [c2 -  -  - ]
  `).s("sawtooth")
    .lpf(800)
    .gain(0.7)
    .room(0.2),
  
  // Piano chords - full voicings holding for 4 beats each
  note(`
  [[e3,g3,b3,e4] -  -  - ] [-  -  -  - ] [-  -  -  - ] [-  -  -  - ],
  [-  -  -  - ] [[g3,b3,d4,g4] -  -  - ] [-  -  -  - ] [-  -  -  - ],
  [-  -  -  - ] [-  -  -  - ] [[b3,d4,fs4,b4] -  -  - ] [-  -  -  - ],
  [-  -  -  - ] [-  -  -  - ] [-  -  -  - ] [[c4,e4,g4,c5] -  -  - ]
  `).s("piano")
    .velocity(0.6)
    .gain(0.7)
    .room(0.4),
  
  // Lead melody walking through chord changes
  note("<[e4 g4 b4 d5] [g4 b4 d5 g5] [b4 d5 f#5 b5] [c5 e5 g5 a5]>")
    .s("square")
    .lpf(sine.range(800,2400))
    .gain(0.4)
    .room(0.4)
    .delay(0.3)
)
