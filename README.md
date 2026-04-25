# homeassistant-dte-current-price
Home Assistant Template Resource for DTE rates

## Rates
Includes D1.1, D1.2, D1.7, and D1.11 rates based on the latest DTE Electric rate book.
The inflow values are total marginal rates that combine the tariff base energy charges, distribution charge, and the tariff surcharge totals from DTE's C8.5 and C9.8 sections.
D1.1 is included for separately metered interruptible space conditioning / AC service.
Rates were updated from the Michigan Public Service Commission PDF:
https://www.michigan.gov/-/media/Project/Websites/mpsc/consumer/rate-books/electric/dte/dtee1cur.pdf

## Installation
Copy the rate(s) that you are interested in into your home assistant `configuration.yaml` file into the `template:` section (create it if it doesn't exist).