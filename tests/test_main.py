# tests/test_main.py
import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main


# --- detect_sender tests ---

def test_detect_sender_nested_dict_owner():
    """Handles owner as {"AddressOwner": "0xABC"} format."""
    changes = [
        {"coinType": "0x2::sui::SUI", "amount": "-5000000", "owner": {"AddressOwner": "0xSENDER"}},
        {"coinType": "0x2::sui::SUI", "amount": "5000000", "owner": {"AddressOwner": "0xRECIPIENT"}},
    ]
    assert main.detect_sender(changes) == "0xSENDER"


def test_detect_sender_plain_string_owner():
    """Handles owner as plain address string format."""
    changes = [
        {"coinType": "0x2::sui::SUI", "amount": "-5000000", "owner": "0xSENDER"},
    ]
    assert main.detect_sender(changes) == "0xSENDER"


def test_detect_sender_most_negative_wins():
    """Returns the address with the largest negative SUI amount."""
    changes = [
        {"coinType": "0x2::sui::SUI", "amount": "-1000000", "owner": "0xA"},
        {"coinType": "0x2::sui::SUI", "amount": "-9000000", "owner": "0xSENDER"},
        {"coinType": "0x2::sui::SUI", "amount": "-500000", "owner": "0xB"},
    ]
    assert main.detect_sender(changes) == "0xSENDER"


def test_detect_sender_ignores_non_sui_coins():
    """Ignores balance changes for non-SUI coin types."""
    changes = [
        {"coinType": "0xDEAD::usdc::USDC", "amount": "-100000000", "owner": "0xWRONG"},
        {"coinType": "0x2::sui::SUI", "amount": "-5000000", "owner": "0xSENDER"},
    ]
    assert main.detect_sender(changes) == "0xSENDER"


def test_detect_sender_no_negative_exits():
    """Exits with code 1 if no negative SUI balance change found."""
    changes = [
        {"coinType": "0x2::sui::SUI", "amount": "5000000", "owner": "0xA"},
    ]
    with pytest.raises(SystemExit) as exc:
        main.detect_sender(changes)
    assert exc.value.code == 1
