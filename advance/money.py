import re

_AMOUNT_RE = re.compile(r"^\d+\.\d{2}$")


def parse_kopecks(raw: str, *, source: str, line_no: int) -> int:
    if not _AMOUNT_RE.fullmatch(raw):
        raise ValueError(f"Некорректная сумма {raw!r} в {source}, строка {line_no}")
    rubles, kopecks = raw.split(".")
    return int(rubles) * 100 + int(kopecks)


def format_rub(kopecks: int) -> str:
    sign = "-" if kopecks < 0 else ""
    value = abs(kopecks)
    rubles, kop = divmod(value, 100)
    rub_str = f"{rubles:,}".replace(",", " ")
    return f"{sign}{rub_str},{kop:02d}"


def format_rub_csv(kopecks: int) -> str:
    sign = "-" if kopecks < 0 else ""
    value = abs(kopecks)
    rubles, kop = divmod(value, 100)
    return f"{sign}{rubles},{kop:02d}"
