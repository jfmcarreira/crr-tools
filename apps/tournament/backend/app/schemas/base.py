from typing import Annotated

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, StringConstraints
from pydantic.alias_generators import to_camel

MAX_SAFE_INTEGER = 9007199254740991


class Schema(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="ignore")


class RequestSchema(Schema):
    model_config = ConfigDict(populate_by_name=False, validate_by_name=False, validate_by_alias=True)


def number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("Expected a JSON number")
    return value


def identifier(value):
    # URL IDs and team group IDs accept numeric coercion.
    try:
        if isinstance(value, str):
            value = value.strip()
            if value.lower().startswith(("0x", "0b", "0o")):
                return int(value, 0)
            return float(value or "0")
        return int(value) if isinstance(value, bool) else value
    except (ValueError, OverflowError):
        raise ValueError("Invalid identifier") from None


PositiveInt = Annotated[int, BeforeValidator(number), Field(ge=1, le=MAX_SAFE_INTEGER)]
PositiveId = Annotated[int, BeforeValidator(identifier), Field(ge=1, le=MAX_SAFE_INTEGER)]
Score = Annotated[int, BeforeValidator(number), Field(ge=0, le=MAX_SAFE_INTEGER)]
JS_WHITESPACE = "\t\n\v\f\r \u00a0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a\u2028\u2029\u202f\u205f\u3000\ufeff"


def name(value):
    if not isinstance(value, str):
        raise ValueError("Expected a string")
    value = value.strip(JS_WHITESPACE)
    if not 1 <= len(value.encode("utf-16-le", errors="surrogatepass")) // 2 <= 200:
        raise ValueError("Invalid name length")
    return value


Name = Annotated[str, BeforeValidator(name), StringConstraints(strict=True, min_length=1, max_length=200)]


def confirmed(value):
    if value is not True:
        raise ValueError("Confirmation must be true")
    return value


Confirmed = Annotated[bool, BeforeValidator(confirmed)]


class Confirmation(RequestSchema):
    confirm: Confirmed = False
