# WiZ Music Sync for Windows

Your WiZ bulb changes colour and brightness to the beat of anything playing on your laptop.
The sound is held back by exactly the bulb's delay, so what you hear and what you see happen together.

## What's in this folder

| File | What it is |
|---|---|
| `build.bat` | **Double-click once.** Builds the app into `dist\WiZ Music Sync\` and adds a Desktop shortcut (first build downloads about 80 MB) |
| `run.bat` | Runs the app directly with Python, with no build needed (handy for testing) |
| `app.py` | The app window (Qt) |
| `wiz_core.py` | The engine: beat detection, bulb control, audio delay |
| `assets\` | App icon and UI images |

After building, `dist\WiZ Music Sync\` is the finished app. Copy that folder anywhere, even to
another PC with no Python. Settings are saved next to the .exe in `settings.json`.

## One-time setup

1. **Python** (only needed to build): from python.org, with "Add python.exe to PATH" ticked.
2. **VB-Cable**: install from vb-audio.com/Cable (the app has a button for it), then **restart Windows**.
3. Double-click **`build.bat`**. When it's finished, open **WiZ Music Sync** from your Desktop.
4. If Windows Firewall asks, click **Allow** (private networks). The app needs this to talk to the bulb.

## Using the app

1. **Bulb**: click **Find bulbs**, then **Test bulb**. It should flash red, green, then blue.
   If the test says the bulb refuses commands, turn on *Allow all controls* in the WiZ app
   (Settings > Security > Allow local communication), or add your signing key.
2. **Sound**: click **Open Sound settings**. On the Playback tab, select **CABLE Input**, then **Set Default**.
   Back in the app, click **Refresh**, then choose your headphones or speakers under **Play through**.
3. **Sync test**: click **Start sync test**. The bulb flashes and you hear a tick every second.
   Drag the slider (or use the ±1 / ±10 ms buttons) until they happen at the same moment, then click **Stop sync test**.
   - Tick before the flash: move right (more delay)
   - Flash before the tick: move left
   - Negative values hold back the light instead (for Bluetooth headphones that lag more than the bulb)
4. Click **Start music sync** and play songs in any app. The preview shows the colour the bulb is getting, a ring for every beat, and a history of recent beats.

Run the sync test again whenever you switch headphones, speakers or Wi-Fi network.
Everything is saved automatically.

## Look & feel

- **Colours**: click a palette chip: Party, Rainbow, Fire, Ocean or Neon
- **Colour changes**: how often softer beats change colour (strong hits always change it)
- **Big-hit contrast**: higher means only the biggest hits reach full power
- **Beat threshold**: lower gives more flashes, higher gives only clear beats
- **Min / Max brightness**: the brightness range

All of these apply instantly while the music is playing.

## Troubleshooting

- **No sound**: check that **Play through** is your headphones. When you're finished, set your headphones
  back as the default device in Sound settings to get normal sound.
- **Crackles**: close other audio apps, or try your speakers or another device.
- **Bulb lags sometimes**: that's Wi-Fi jitter. A strong signal and a router (rather than a phone hotspot) help.
- **"Bulb refused the command"**: see step 1 of *Using the app* above.
- **Videos look ahead of their sound**: that's expected while sync is on, because the sound is delayed. Stop sync for movies.
