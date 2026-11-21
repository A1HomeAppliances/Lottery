import re

_DIGIT_TABLE = str.maketrans(
    "۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789"
)


def digits_only(text):
    return re.sub(r"\D", "", str(text).translate(_DIGIT_TABLE))


def normalize_phone(raw):
    d = digits_only(raw)
    if d.startswith("0098"):
        d = "0" + d[4:]
    elif d.startswith("98") and len(d) == 12:
        d = "0" + d[2:]
    elif len(d) == 10 and d.startswith("9"):
        d = "0" + d
    return d if re.fullmatch(r"09\d{9}", d) else None
