# homeassistant-dte-current-price

Home Assistant template sensors for DTE Electric residential time-of-use rates.

## Usage

Pick your schedule, copy the sensor into `configuration.yaml` under `template:`:

| Schedule | File | Description |
|---|---|---|
| D1.1 | [`d1.1.yaml`](d1.1.yaml) | Interruptible Space Conditioning — two flat seasonal rates |
| D1.2 | [`d1.2.yaml`](d1.2.yaml) | Enhanced Time-of-Use — peak/off-peak by season + Outflow sell-back estimate |
| D1.7 | [`d1.7.yaml`](d1.7.yaml) | Geothermal Time-of-Day — peak/off-peak by season |
| D1.11 | [`d1.11.yaml`](d1.11.yaml) | Standard Time-of-Use — peak/off-peak by season |

Each sensor provides a `{{ state }}` in USD/kWh for the current marginal rate (excludes fixed monthly service charges). Add it to an energy dashboard or automation.

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
