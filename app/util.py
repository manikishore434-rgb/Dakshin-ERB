"""Money, quantity and date helpers.

Conventions used everywhere in the code base:
  * money is stored as INTEGER paise (never floats)
  * quantities are stored as INTEGER milli-units of the item's base unit
    (1.5 kg -> 1500, 200 packets -> 200000)
  * rates are handled as Decimal and rounded half-up once, at the line level
"""
import datetime as dt
from decimal import Decimal, ROUND_HALF_UP


class ServiceError(Exception):
    """Business-rule violation that should be shown to the user."""


def D(x) -> Decimal:
    return x if isinstance(x, Decimal) else Decimal(str(x))


def round_half_up(x) -> int:
    return int(D(x).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def to_paise(rupees) -> int:
    return round_half_up(D(rupees) * 100)


def to_milli(q) -> int:
    return round_half_up(D(q) * 1000)


def _indian_group(n: int) -> str:
    s = str(n)
    if len(s) <= 3:
        return s
    head, tail = s[:-3], s[-3:]
    parts = []
    while len(head) > 2:
        parts.insert(0, head[-2:])
        head = head[:-2]
    if head:
        parts.insert(0, head)
    return ",".join(parts + [tail])


def money(p) -> str:
    p = int(p or 0)
    sign = "-" if p < 0 else ""
    r, f = divmod(abs(p), 100)
    return f"{sign}{_indian_group(r)}.{f:02d}"


def qty(m) -> str:
    d = D(int(m or 0)) / 1000
    return format(d.normalize(), "f")


def pct(planned: int, actual: int):
    """Variance of actual vs planned as a Decimal percentage (2 dp), None if planned is 0."""
    if not planned:
        return None
    return (D(actual - planned) * 100 / D(planned)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def beyond_tolerance(planned: int, actual: int, tol_bp: int) -> bool:
    """True when |actual-planned| / planned is strictly greater than tolerance (basis points)."""
    if planned == 0:
        return actual != 0
    return abs(actual - planned) * 10000 > tol_bp * planned


def today() -> str:
    return dt.date.today().isoformat()


def fy_of(date_iso: str) -> str:
    d = dt.date.fromisoformat(date_iso)
    start = d.year if d.month >= 4 else d.year - 1
    return f"{start}-{str(start + 1)[-2:]}"


_ONES = ("Zero One Two Three Four Five Six Seven Eight Nine Ten Eleven Twelve Thirteen Fourteen Fifteen "
         "Sixteen Seventeen Eighteen Nineteen").split()
_TENS = "Twenty Thirty Forty Fifty Sixty Seventy Eighty Ninety".split()


def _words(n: int) -> str:
    if n < 20:
        return _ONES[n]
    if n < 100:
        return _TENS[n // 10 - 2] + ("" if n % 10 == 0 else " " + _ONES[n % 10])
    if n < 1000:
        return _ONES[n // 100] + " Hundred" + ("" if n % 100 == 0 else " " + _words(n % 100))
    for div, name in ((10000000, "Crore"), (100000, "Lakh"), (1000, "Thousand")):
        if n >= div:
            return _words(n // div) + " " + name + ("" if n % div == 0 else " " + _words(n % div))
    return str(n)


def amount_in_words(paise: int) -> str:
    r, p = divmod(int(paise), 100)
    s = "Rupees " + (_words(r) if r else "Zero")
    if p:
        s += " and " + _words(p) + " Paise"
    return s + " Only"
