Kilin Kolin is a brawler game that picks a random person from Wikipedia.

Beating a person unlocks the people linked from their Wikipedia page. Unlocked
people walk into the arena from its edges over time, with up to four fighting at
once. A defeated person is saved in `wikigraph/save.json` and is never spawned
again. The same save also caches discovered connections and the current pool of
possible enemies. If a page has no usable direct connections, the game searches
two links deep; if that is also empty, it adds a new random person instead.
Connections are prefetched when an opponent enters the arena, but remain locked
until that opponent is defeated.

The save is a forest with top-level `allDefeated`, `allPending`, and `trees`
fields. Each tree recursively nests people under a keyed `connections` object.
The game window includes a right-hand queue showing people who are unlocked but
not currently fighting.

Wikipedia article byte length determines each enemy's total stat-point budget.
Those points are distributed deterministically but unevenly between health,
speed, damage, turning, and aggression, so people with similarly long articles
can still fight very differently. The waiting queue previews every allocation.
The player gains health, movement, turning, and damage strength with each defeat.

The goal is to defeat hitler.


--

# gameplay

Top down brawler with 360 rotation

Controls.
W: Forward
S: Backwards
Left-Shift: Toggle lock on the closest enemy

A: Turn left / Strafe when locked in
D: Turn right / Strafe when locked in
Q: Fast 90 degrees turn to left / Strafe dash left when locked in
E: Fast 90 degress turn to right / Strafe dash right when locked in

J: Charge up left punch / weapon (release to swing / use / shoot)
K: Charge up right punch / weapon (release to swing / use / shoot)
U: Left sweeping kick
I: Right sweeping kick

Charging slows movement. At 35% health or below, desperation overcharge becomes
available: punches can be charged far beyond the normal limit for much stronger
knockback. Flung entities damage other entities on a hard collision and take damage
when they hit an arena wall at high speed. Defeated enemies remain as tumbling
ragdolls and despawn only after their movement has completely settled.

Kicks plant the entity in place and sweep a foot through a wide arc. They deal less
damage than a strong punch but cover the sides and knock targets along the sweep,
making them useful against strafing opponents.


## Run the prototype

```bash
python game.py
```

Install the dependency first with `pip install -r requirements.txt` if needed.

The prototype uses simple drawn shapes: the player is a blue ball, the hands are
small balls, and the feet are small ovals. Hold J or K to charge the matching hand,
then release to punch. U and I kick immediately. Press R after winning or losing to
restart, or Escape to quit.
