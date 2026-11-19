# EZAppy — desktop monitor for APsystems EZ1

A small dashboard you run on your PC to watch an **APsystems EZ1 microinverter** over your home
network, with no cloud account. It reads the EZ1's local API, keeps a history in a local SQLite file
and shows it in your browser:

- Power now (total and per panel) against the output limit
- Energy today and lifetime
- Power over the last 6 h / 24 h / 7 days
- Daily energy for the last 14 / 30 / 90 days
- Alarms (off-grid, DC short circuit, output fault) and device details

Needs only **Python 3.9+**: no packages to install.

## 1. Turn on Local Mode on the inverter

In the **AP EasyPower** phone app, connect to the inverter, open **Settings → Local Mode**, switch it
on and choose **Continuous**. Note the **IP address** it shows (e.g. `192.168.1.50`). It's worth
reserving that address in your router (DHCP reservation) so it doesn't change.

## 2. Run it

```bash
git clone https://github.com/bantachris-commits/EZAppy.git
cd EZAppy
python -m ez1monitor --inverter 192.168.1.50
```

On Windows use `py` instead of `python` if `python` isn't found. Then open
**http://localhost:8080**.

Check the connection without starting the dashboard:

```bash
python -m ez1monitor --inverter 192.168.1.50 --check
```

Try it with no inverter (simulated data and two weeks of fake history):

```bash
python -m ez1monitor --demo
```

### Options

| Option | Default | What it does |
|---|---|---|
| `--inverter IP` | `$EZ1_HOST` | The EZ1's IP address |
| `--port N` | `8080` | Dashboard port |
| `--bind ADDR` | `127.0.0.1` | Use `0.0.0.0` to open the dashboard from other devices on your LAN |
| `--interval S` | `15` | Seconds between readings (the poller drops to once a minute while the inverter is offline) |
| `--db FILE` | `ez1-history.sqlite3` | Where history is stored (raw readings kept 90 days, daily totals kept forever) |
| `-v` | | Verbose logging |

## Things to know

- **The EZ1 is powered by the panels**, so it disappears from the network at night. The dashboard shows
  "Inverter offline (normal at night)" and picks up again in the morning.
- The phone app and this monitor can run at the same time.
- History only covers the time this monitor was running. For a complete record, leave it running on
  an always-on machine (a spare PC, NAS or Raspberry Pi) with `--bind 0.0.0.0`, then open it from any
  device at `http://<that-machine>:8080`.
- Daily energy is taken from the inverter's lifetime counter, so a mid-day inverter restart (e.g. heavy
  cloud) doesn't lose the morning's production.

## Start automatically

- **Windows:** create a shortcut to `pythonw -m ez1monitor --inverter 192.168.1.50` with "Start in" set to
  the EZAppy folder, and put it in `shell:startup`.
- **macOS / Linux:** add a login item, a `launchd` agent, or a `systemd --user` service running the same
  command.

## Development

```bash
python -m unittest discover -s tests -t .   # tests run against the built-in simulator
python -m ez1monitor.simulator 8050         # standalone fake EZ1 on port 8050
```

Layout: `ez1monitor/ez1.py` (API client), `store.py` (SQLite history), `server.py` (poller + HTTP
server), `static/index.html` (dashboard), `simulator.py` (fake inverter).

EZ1 local API endpoints used (all `GET http://<ip>:8050/...`): `getDeviceInfo`, `getOutputData`,
`getMaxPower`, `getAlarm`, `getOnOff`. This app is read-only: it never changes inverter settings.
