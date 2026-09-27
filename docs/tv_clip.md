# The TV clip

The viewer can show the real footage of a possession beside the animation, frame-synced, so a reader can check with their own eyes that
the reconstruction matches the game. The clip is **shown, never read**: no number anywhere comes from it, and no clip is part of this
repository (broadcast footage is not ours to publish, and the competition allows only SkillCorner's data).

## How to use it with a clip of your own

1. Put a folder `broadcast/` at the root of the lab (next to `src/`; git ignores it), or point `COURTLAB_BROADCAST` at any folder.
2. Drop the clip in it and write a `sync.json` that says where the release of the shot is inside the clip:

```json
{ "chance-191313-1-7": { "file": "191313_chance-191313-1-7.mp4", "release_s": 6.48 } }
```

`release_s` is the second of the clip at which the ball leaves the shooter's hand; the viewer pairs it with the release frame of the
possession and plays the two together. A copy with a keyframe every second (`ffmpeg -g 25`) makes the seeking exact.

3. `courtlab serve` reports the folder it found. In a play, the **TV clip** control appears in the control row (and `?bc=1` turns it on);
   click the window to make it large. Without a clip the control never shows and nothing else changes.

## What the clip was used for here

Two checks, both written up in [data_notes.md](data_notes.md): the raw tracking frame is a mirror of the real court, and SkillCorner's
clocks run about 0.6 s behind the arena display. Both were established by looking, then verified in the data, player by player.
