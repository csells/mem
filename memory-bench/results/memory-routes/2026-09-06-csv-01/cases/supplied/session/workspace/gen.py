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
    f.write("\n")
print("config.json written")

rows = [
    {"client": 'Café "North", LLC;\tWest', "amount": "12.34565"},
    {"client": "South & Sons",             "amount": "-0.01005"},
    {"client": "East",                     "amount": "0"},
]

quantize_str = Decimal("0.0000")

def fmt_amount(s):
    d = Decimal(s)
    rounded = d.quantize(quantize_str, rounding=ROUND_HALF_UP)
    return format(rounded, "f")

def csv_field(value, delimiter):
    if any(c in value for c in (delimiter, '"', "\n", "\r")):
        return '"' + value.replace('"', '""') + '"'
    return value

delimiter = "\t"
line_ending = "\n"

lines = []
lines.append("client" + delimiter + "amount")
for row in rows:
    lines.append(csv_field(row["client"], delimiter) + delimiter + fmt_amount(row["amount"]))

csv_content = line_ending.join(lines) + line_ending

with open("invoices.csv", "w", encoding="utf-8", newline="") as f:
    f.write(csv_content)
print("invoices.csv written")

print("\n--- preview (repr per line) ---")
for line in lines:
    print(repr(line))
