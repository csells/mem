import json
from decimal import Decimal, ROUND_HALF_UP

config = {
    "project": "acme-finance",
    "csv_export": {
        "delimiter": "\t",
        "encoding": "utf-8",
        "line_ending": "LF",
        "decimal_places": 4,
        "decimal_separator": "."
    }
}

with open("config.json", "w", encoding="utf-8") as f:
    json.dump(config, f, indent=2)

rows = [
    {"client": 'Café "North", LLC;\tWest', "amount": "12.34565"},
    {"client": "South & Sons",                   "amount": "-0.01005"},
    {"client": "East",                           "amount": "0"},
]

dp = config["csv_export"]["decimal_places"]
quant = Decimal("0." + "0" * dp)

def fmt_amount(s):
    d = Decimal(s).quantize(quant, rounding=ROUND_HALF_UP)
    return format(d, 'f')

delimiter = config["csv_export"]["delimiter"]
line_ending = "\n"

def csv_cell(val):
    if any(c in val for c in [delimiter, '"', '\n', '\r']):
        return '"' + val.replace('"', '""') + '"'
    return val

lines = []
lines.append(csv_cell("client") + delimiter + csv_cell("amount"))
for r in rows:
    lines.append(csv_cell(r["client"]) + delimiter + fmt_amount(r["amount"]))

content = line_ending.join(lines) + line_ending

with open("invoices.csv", "w", encoding="utf-8", newline="") as f:
    f.write(content)

print("Done")
print("Amounts:", [fmt_amount(r["amount"]) for r in rows])
print("CSV repr:", repr(content))
