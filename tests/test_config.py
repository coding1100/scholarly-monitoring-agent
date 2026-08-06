from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.config import (
    Settings,
    get_env_monitor_name,
    normalize_and_validate_url,
    parse_url_checks,
)


def test_parse_url_checks_two_valid_urls() -> None:
    urls = parse_url_checks("https://scholarlyhelp.com/,https://mindrind.net/")
    assert urls == ["https://scholarlyhelp.com/", "https://mindrind.net/"]


def test_parse_url_checks_whitespace_around_comma_separated_entries() -> None:
    urls = parse_url_checks(" https://scholarlyhelp.com/ , https://mindrind.net/ ")
    assert urls == ["https://scholarlyhelp.com/", "https://mindrind.net/"]


def test_parse_url_checks_empty_entries_ignored() -> None:
    urls = parse_url_checks(" https://scholarlyhelp.com/ , , https://mindrind.net/ , ")
    assert urls == ["https://scholarlyhelp.com/", "https://mindrind.net/"]


def test_parse_url_checks_duplicate_urls_removed() -> None:
    urls = parse_url_checks(
        "https://scholarlyhelp.com/,https://mindrind.net/,https://scholarlyhelp.com/"
    )
    assert urls == ["https://scholarlyhelp.com/", "https://mindrind.net/"]


def test_parse_url_checks_same_url_with_and_without_trailing_slash_deduplicated() -> None:
    urls = parse_url_checks(
        " https://scholarlyhelp.com/ , https://mindrind.net/ , https://scholarlyhelp.com "
    )
    assert urls == ["https://scholarlyhelp.com/", "https://mindrind.net/"]


def test_parse_url_checks_invalid_url_rejected() -> None:
    with pytest.raises(ValueError, match="Invalid URL"):
        parse_url_checks("https://scholarlyhelp.com/, invalid-url")


def test_parse_url_checks_unsupported_scheme_rejected() -> None:
    with pytest.raises(ValueError, match="Only http and https are allowed"):
        parse_url_checks("ftp://scholarlyhelp.com/")


def test_url_check_fallback_works() -> None:
    settings = Settings(URL_CHECKS="", URL_CHECK="https://scholarlyhelp.com/")
    assert settings.parsed_url_checks == ["https://scholarlyhelp.com/"]


def test_url_checks_takes_precedence_over_url_check() -> None:
    settings = Settings(
        URL_CHECKS="https://scholarlyhelp.com/,https://mindrind.net/",
        URL_CHECK="https://fallback.com/",
    )
    assert settings.parsed_url_checks == [
        "https://scholarlyhelp.com/",
        "https://mindrind.net/",
    ]


def test_both_empty_produces_no_environment_monitors() -> None:
    settings = Settings(URL_CHECKS="", URL_CHECK="")
    assert settings.parsed_url_checks == []


def test_settings_validation_fails_on_invalid_url_checks() -> None:
    with pytest.raises(ValidationError):
        Settings(URL_CHECKS="https://scholarlyhelp.com/,not_a_valid_url")


def test_get_env_monitor_name_deterministic() -> None:
    name1 = get_env_monitor_name("https://scholarlyhelp.com/")
    name2 = get_env_monitor_name("https://mindrind.net/")
    assert name1 == "env-url-check-scholarlyhelp-com"
    assert name2 == "env-url-check-mindrind-net"


def test_normalize_and_validate_url_root_path() -> None:
    assert (
        normalize_and_validate_url("https://scholarlyhelp.com")
        == "https://scholarlyhelp.com/"
    )
    assert (
        normalize_and_validate_url("HTTPS://SCHOLARLYHELP.COM/")
        == "https://scholarlyhelp.com/"
    )
