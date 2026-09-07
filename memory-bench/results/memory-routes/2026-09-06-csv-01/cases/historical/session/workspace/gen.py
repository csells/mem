import decimal
import json

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
    {"client": "South & Sons",             "amount": "-0.01005"},
    {"client": "East",                     "amount": "0"},
]

decimal_places = 4
decimal_separator = "."
delimiter = "\t"
line_ending = "\n"

def format_amount(amount_str, places):
    d = decimal.Decimal(amount_str)
    q = decimal.Decimal("1." + "0" * places)
    rounded = d.quantize(q, rounding=decimal.ROUND_HALF_UP)
    s = str(rounded)
    if decimal_separator != ".":
        s = s.replace(".", decimal_separator)
    return s

def csv_field(value, delim):
    if delim in value or '"' in value or '\n' in value or '\r' in value:
        return '"' + value.replace('"', '""') + '"'
    return value

lines = []
lines.append("client" + delimiter + "amount")
for row in rows:
    client = csv_field(row["client"], delimiter)
    amount = format_amount(row["amount"], decimal_places)
    lines.append(client + delimiter + amount)

csv_content = line_ending.join(lines) + line_ending

with open("invoices.csv", "w", encoding="utf-8", newline="") as f:
    f.write(csv_content)

print("config.json written")
print("invoices.csv written")
print()
print("--- config.json ---")
print(open("config.json").read())
print()
print("--- invoices.csv bytes ---")
with open("invoices.csv", "rb") as f:
    raw = f.read()
print(repr(raw))
print()
for row in rows:
    print(f"  {row['amount']} -> {format_amount(row['amount'], 4)}")
