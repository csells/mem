import json
from decimal import Decimal, ROUND_HALF_UP

config = {
    "project": "acme-finance",
    "csv_export": {
        "delimiter": ";",
        "encoding": "utf-8",
        "line_ending": "LF",
        "decimal_places": 4,
        "decimal_separator": "."
    }
}

with open('/private/tmp/mem-csv-w1g_gczn/current/work/config.json', 'w', encoding='utf-8') as f:
    json.dump(config, f, indent=2)
    f.write('\n')

print("config.json written")

delimiter = ";"
line_ending = "\n"
decimal_places = 4
decimal_separator = "."

rows = [
    {"client": 'Café "North", LLC;\tWest', "amount": "12.34565"},
    {"client": "South & Sons",                   "amount": "-0.01005"},
    {"client": "East",                           "amount": "0"},
]

def round_amount(amount_str, places):
    d = Decimal(amount_str)
    quantize_str = Decimal('1.' + '0' * places)
    return d.quantize(quantize_str, rounding=ROUND_HALF_UP)

def csv_field(value, delim):
    needs_quote = (delim in value or '"' in value or '\n' in value or '\r' in value)
    if needs_quote:
        value = '"' + value.replace('"', '""') + '"'
    return value

lines = ["client" + delimiter + "amount"]
for row in rows:
    client = row["client"]
    amount = round_amount(row["amount"], decimal_places)
    amount_str = format(amount, 'f')
    if decimal_separator != ".":
        amount_str = amount_str.replace(".", decimal_separator)
    client_field = csv_field(client, delimiter)
    lines.append(client_field + delimiter + amount_str)

csv_content = line_ending.join(lines) + line_ending

with open('/private/tmp/mem-csv-w1g_gczn/current/work/invoices.csv', 'wb') as f:
    f.write(csv_content.encode('utf-8'))

print("invoices.csv written")
print("\n--- CSV content (repr) ---")
print(repr(csv_content))
print("\n--- Amounts ---")
for row in rows:
    a = round_amount(row["amount"], decimal_places)
    print(f"  {row['amount']} -> {a}")
