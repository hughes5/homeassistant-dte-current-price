# homeassistant-dte-current-price

Home Assistant template sensors for DTE Electric residential time-of-use rates.

## Usage

Pick your schedule and install its YAML as a Home Assistant package. Keeping the generated YAML in its own package file is easier to inspect, replace, and remove than pasting generated content into `configuration.yaml`.

| Schedule | File | Description |
|---|---|---|
| D1.1 | [`d1.1.yaml`](d1.1.yaml) | Interruptible Space Conditioning — two flat seasonal rates |
| D1.2 | [`d1.2.yaml`](d1.2.yaml) | Enhanced Time-of-Use — peak/off-peak by season + Outflow sell-back estimate |
| D1.7 | [`d1.7.yaml`](d1.7.yaml) | Geothermal Time-of-Day — peak/off-peak by season |
| D1.11 | [`d1.11.yaml`](d1.11.yaml) | Standard Time-of-Use — peak/off-peak by season |

Each sensor provides a `{{ state }}` in USD/kWh for the current marginal rate (excludes fixed monthly service charges). Add it to an energy dashboard or automation.

## Home Assistant install/update options

Quick-start setup: you can open a schedule file above and paste its contents directly into `configuration.yaml`.

Recommended manual setup: enable packages, then copy the schedule YAML you need into a separate file such as `/config/packages/dte-d1.11.yaml`.

Automated setup: use a Home Assistant package and download the latest released template for your rate schedule from the release asset URL. The update script below creates the package file the first time it runs, then replaces it on later runs.

Enable packages in `configuration.yaml`:

```yaml
homeassistant:
  packages: !include_dir_named packages
```

Create the script directory from the Terminal & SSH add-on:

```sh
mkdir -p /config/scripts
```

Create `/config/scripts/update_dte_rate_template.sh` in Home Assistant:

```sh
#!/bin/sh
set -eu

schedule="${1:-d1.11}"
dest="/config/packages/dte-${schedule}.yaml"
tmp="${dest}.tmp"

mkdir -p "$(dirname "$dest")"

curl -fsSL \
  "https://github.com/hughes5/homeassistant-dte-current-price/releases/latest/download/${schedule}.yaml" \
  -o "$tmp"

mv "$tmp" "$dest"
```

Make it executable from the Terminal & SSH add-on:

```sh
sed -i 's/\r$//' /config/scripts/update_dte_rate_template.sh
chmod +x /config/scripts/update_dte_rate_template.sh
```

Expose the updater as a Home Assistant shell command:

```yaml
shell_command:
  update_dte_rate_template: "/config/scripts/update_dte_rate_template.sh d1.11"
```

Run `/config/scripts/update_dte_rate_template.sh d1.11` once from Terminal & SSH to create the initial package file. Restart Home Assistant after the first setup so it loads the package include and shell command.

After that, run `shell_command.update_dte_rate_template` from an automation or from Developer tools > Actions, then reload Template entities from Developer tools > YAML. The URL above intentionally uses the latest release, not `main`, so Home Assistant only consumes published rate updates.

## Data source

Rates are derived from the [DTE Electric Rate Book](https://www.michigan.gov/-/media/Project/Websites/mpsc/consumer/rate-books/electric/dte/dtee1cur.pdf) published by the Michigan Public Service Commission. The current rates were set in MPSC Case No. U‑21860, effective March 5, 2026. The per-kWh totals are pre-computed from:

- Base energy charges (capacity + non-capacity, per-schedule TOU condition)
- Distribution charge (D1.x residential, from rate schedule page)
- Power supply surcharge total (PSCR + River Rouge Securitization + TCSC Securitization, from C8.5 table)
- Delivery surcharge (from C9.8 table)

Source data lives in [`rates/data.yaml`](rates/data.yaml). A weekly GitHub Action checks the MPSC PDF for PSCR factor changes; if the rate changes the YAML files are regenerated and a release is published.

## Contributing

- Edit [`rates/data.yaml`](rates/data.yaml) — that's the single source of truth
- Run `python3 scripts/generate_rates.py` to regenerate the HA YAML files
- Run `python3 scripts/update_pscr.py --no-download` to test PSCR extraction from the cached PDF
