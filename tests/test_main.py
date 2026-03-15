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


# --- get_address tests ---

def test_get_address_plain_string():
    """Plain string input returns the string itself."""
    assert main.get_address("0xABC") == "0xABC"


def test_get_address_dict_with_address_owner():
    """Dict with AddressOwner key returns the address value."""
    assert main.get_address({"AddressOwner": "0xABC"}) == "0xABC"


def test_get_address_dict_without_address_owner():
    """Dict without AddressOwner key (e.g. Shared) returns None."""
    assert main.get_address({"Shared": {}}) is None


def test_get_address_none_input():
    """Non-string, non-dict input returns None."""
    assert main.get_address(None) is None


# --- detect_sender edge case tests ---

def test_detect_sender_empty_list_exits():
    """Exits with code 1 when balance_changes is an empty list."""
    with pytest.raises(SystemExit) as exc:
        main.detect_sender([])
    assert exc.value.code == 1


# --- audit_balance_changes tests ---

def test_audit_balance_changes_returns_false_when_safe(capsys):
    """Returns False when actual loss is within intended cost + gas buffer."""
    json_data = {
        "balanceChanges": [
            {"coinType": "0x2::sui::SUI", "amount": "-10000000", "owner": "0xSENDER"},
        ]
    }
    result = main.audit_balance_changes(json_data, intended_cost=0.01, owner_addr="0xSENDER")
    assert result is False


def test_audit_balance_changes_returns_true_when_price_mismatch(capsys):
    """Returns True when actual loss exceeds intended cost + 0.02 SUI buffer."""
    json_data = {
        "balanceChanges": [
            # 0.12 SUI drained, user intended 0.01 — exceeds 0.01 + 0.02 buffer
            {"coinType": "0x2::sui::SUI", "amount": "-120000000", "owner": "0xSENDER"},
        ]
    }
    result = main.audit_balance_changes(json_data, intended_cost=0.01, owner_addr="0xSENDER")
    assert result is True


def test_audit_balance_changes_does_not_exit(capsys):
    """Does not call sys.exit() — returns bool so both checks can always run."""
    json_data = {
        "balanceChanges": [
            {"coinType": "0x2::sui::SUI", "amount": "-120000000", "owner": "0xSENDER"},
        ]
    }
    try:
        main.audit_balance_changes(json_data, intended_cost=0.01, owner_addr="0xSENDER")
    except SystemExit:
        pytest.fail("audit_balance_changes() must not call sys.exit()")


def test_audit_balance_changes_no_closing_separator(capsys):
    """Does not print the closing '===' separator — that is printed by main() after both checks."""
    json_data = {
        "balanceChanges": [
            {"coinType": "0x2::sui::SUI", "amount": "-10000000", "owner": "0xSENDER"},
        ]
    }
    main.audit_balance_changes(json_data, intended_cost=0.01, owner_addr="0xSENDER")
    captured = capsys.readouterr()
    lines = captured.out.strip().splitlines()
    # The last meaningful line should be the RESULT line, not a closing '===' separator
    assert not lines[-1].startswith("=" * 10), (
        "audit_balance_changes() must not print the closing separator — main() owns that"
    )


# --- main() arg order tests ---

def test_main_exits_when_too_few_args(monkeypatch):
    """Exits with code 1 when fewer than 3 argv entries are provided."""
    monkeypatch.setattr(sys, "argv", ["main.py", "0.01"])
    with pytest.raises(SystemExit) as exc:
        main.main()
    assert exc.value.code == 1


def test_main_cost_is_argv1_not_argv2(monkeypatch):
    """Cost is argv[1] — a non-float argv[1] exits cleanly with code 1, not argv[2]."""
    monkeypatch.setattr(sys, "argv", ["main.py", "not_a_float", "sui client ptb --gas-budget 1"])
    with pytest.raises(SystemExit) as exc:
        main.main()
    assert exc.value.code == 1


# --- audit_object_changes tests ---

def test_audit_object_changes_returns_empty_when_safe():
    """Returns empty list when no mutated objects are diverted to non-sender."""
    json_data = {
        "objectChanges": [
            {"type": "mutated", "objectId": "0xOBJ1", "owner": {"AddressOwner": "0xSENDER"}},
        ]
    }
    result = main.audit_object_changes(json_data, sender_addr="0xSENDER")
    assert result == []


def test_audit_object_changes_detects_hijack(capsys):
    """Returns list of hijacked objects when mutated object owner is not sender."""
    json_data = {
        "objectChanges": [
            {"type": "mutated", "objectId": "0xOBJ1", "owner": {"AddressOwner": "0xATTACKER"}},
        ]
    }
    result = main.audit_object_changes(json_data, sender_addr="0xSENDER")
    assert len(result) == 1
    assert result[0] == ("0xOBJ1", "0xATTACKER")
    captured = capsys.readouterr()
    assert "HIJACK" in captured.out
    assert "0xOBJ1" in captured.out


def test_audit_object_changes_ignores_transferred_type():
    """Does not flag 'transferred' type objects (only 'mutated' is checked)."""
    json_data = {
        "objectChanges": [
            {"type": "transferred", "objectId": "0xOBJ1", "owner": {"AddressOwner": "0xATTACKER"}},
        ]
    }
    result = main.audit_object_changes(json_data, sender_addr="0xSENDER")
    assert result == []


def test_audit_object_changes_ignores_system_addresses():
    """Does not flag objects owned by known Sui system addresses."""
    for addr in ["0x1", "0x2", "0x3", "0x5", "0x6", "0x7", "0x8"]:
        json_data = {
            "objectChanges": [
                {"type": "mutated", "objectId": "0xOBJ1", "owner": {"AddressOwner": addr}},
            ]
        }
        result = main.audit_object_changes(json_data, sender_addr="0xSENDER")
        assert result == [], f"System address {addr} should not be flagged"


def test_audit_object_changes_handles_plain_string_owner(capsys):
    """Handles owner as a plain address string (not nested dict) — detects hijack and warns."""
    json_data = {
        "objectChanges": [
            {"type": "mutated", "objectId": "0xOBJ1", "owner": "0xATTACKER"},
        ]
    }
    result = main.audit_object_changes(json_data, sender_addr="0xSENDER")
    assert len(result) == 1
    assert result[0] == ("0xOBJ1", "0xATTACKER")
    captured = capsys.readouterr()
    assert "HIJACK" in captured.out


def test_audit_object_changes_multiple_hijacks():
    """Detects and returns all hijacked objects."""
    json_data = {
        "objectChanges": [
            {"type": "mutated", "objectId": "0xOBJ1", "owner": "0xATTACKER"},
            {"type": "mutated", "objectId": "0xOBJ2", "owner": "0xSENDER"},  # safe
            {"type": "mutated", "objectId": "0xOBJ3", "owner": "0xATTACKER"},
        ]
    }
    result = main.audit_object_changes(json_data, sender_addr="0xSENDER")
    assert len(result) == 2


def test_audit_object_changes_flags_non_system_address_0x4():
    """0x4 is not in SYSTEM_ADDRESSES — objects owned by 0x4 should be flagged."""
    json_data = {
        "objectChanges": [
            {"type": "mutated", "objectId": "0xOBJ1", "owner": {"AddressOwner": "0x4"}},
        ]
    }
    result = main.audit_object_changes(json_data, sender_addr="0xSENDER")
    assert len(result) == 1, "0x4 is not a trusted system address and should be flagged as HIJACK"


def test_audit_object_changes_missing_key_returns_empty():
    """Returns empty list when 'objectChanges' key is absent from json_data."""
    result = main.audit_object_changes({}, sender_addr="0xSENDER")
    assert result == []
