Kilin Kolin Game is brawler game that pics a random person from wikipedia.

Beating a person spawns in all the connected people as new enemies.

The goal is to defeat hitler.


--

# gameplay

Top down brawler with 360 rotation

Controls.
W: Forward
S: Backwards
A: Turn left
D: Turn right
Q: Fast 90 degrees turn to left
E: Fast 90 degress turn to right

J: Charge up left punch / weapon (release to swing / use / shoot)
K: Charge up right punch / weapon (release to swing / use / shoot)
U: Left kick
I: Right kick

## Run the prototype

```bash
python game.py
```

Install the dependency first with `pip install -r requirements.txt` if needed.

The prototype uses simple drawn shapes: the player is a blue ball, the hands are
small balls, and the feet are small ovals. Hold J or K to charge the matching hand,
then release to punch. U and I kick immediately. Press R after winning or losing to
restart, or Escape to quit.
r pu