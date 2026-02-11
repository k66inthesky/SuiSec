import subprocess
import json
import sys
import os
import re

# =============================================================================
# ANSI Color Constants for Hackathon Demo Output
# =============================================================================
BOLD = "\033[1m"
DIM = "\033[2m"
RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
MAGENTA = "\033[95m"
CYAN = "\033[96m"
WHITE = "\033[97m"
BG_RED = "\033[41m"
BG_GREEN = "\033[42m"
BG_YELLOW = "\033[43m"
RESET = "\033[0m"

# =============================================================================
# Sui CLI Output Parsing
#
# Sui CLI v1.65.x on macOS ignores --json and ALWAYS outputs ASCII box-drawing
# tables with key-value blocks like:
#
#   │  ┌──                                                          │
#   │  │ Owner: Account Address ( 0x...deadbeef )                   │
#   │  │ CoinType: 0x2::sui::SUI                                    │
#   │  │ Amount: 100000000                                          │
#   │  └──                                                          │
#
# The parser below handles this real-world format.
# =============================================================================

def _extract_table_address(raw_value):
    """
    Extract a 0x... address from Sui CLI's 'Account Address ( 0x... )' format.
    Also handles plain '0x...' strings.
    """
    match = re.search(r'(0x[0-9a-fA-F]+)', raw_value)
    return match.group(1) if match else raw_value.strip()


def _parse_kv_blocks(text, section_header):
    """
    Find a named section in Sui CLI ASCII output, then extract all
    key-value blocks (delimited by ┌── ... └──) within that section.

    Returns a list of dicts, one per block, e.g.:
      [{"Owner": "0xabc...", "CoinType": "0x2::sui::SUI", "Amount": "-100000000"}, ...]
    """
    lines = text.splitlines()
    blocks = []

    # Phase 1: find the section start
    in_section = False
    section_lines = []

    for line in lines:
        stripped = line.strip()

        if not in_section:
            if section_header.lower() in stripped.lower():
                in_section = True
            continue

        # Stop when we hit the NEXT top-level section box (╭ or a new section header)
        if re.match(r'^╭', stripped) or re.match(r'^Dry run completed', stripped):
            break

        section_lines.append(line)

    if not section_lines:
        return []

    # Phase 2: split section into ┌── ... └── blocks and parse key: value pairs
    current_block = {}
    in_block = False

    for line in section_lines:
        stripped = line.strip()
        cleaned = re.sub(r'^[│┌└┐┘├┤╭╮╰╯─┬┴┼\s]+', '', stripped)
        cleaned = re.sub(r'[│┌└┐┘├┤╭╮╰╯─┬┴┼\s]+$', '', cleaned)

        if '┌' in stripped:
            in_block = True
            current_block = {}
            continue

        if '└' in stripped:
            if current_block:
                blocks.append(current_block)
            in_block = False
            current_block = {}
            continue

        if not in_block:
            continue

        if ':' in cleaned:
            key, _, value = cleaned.partition(':')
            key = key.strip()
            value = value.strip()
            if key:
                current_block[key] = value

    if current_block:
        blocks.append(current_block)

    return blocks


def _build_structured_data(raw_output):
    """
    Parse the full Sui CLI ASCII output into a structured dict matching
    the JSON shape expected by audit_transaction().
    """
    data = {}

    bc_blocks = _parse_kv_blocks(raw_output, "Balance Changes")
    if bc_blocks:
        balance_changes = []
        for block in bc_blocks:
            raw_owner = block.get("Owner", "")
            addr = _extract_table_address(raw_owner)
            coin_type = block.get("CoinType", "")
            amount = block.get("Amount", "0").replace(",", "").strip()
            balance_changes.append({
                "owner": {"AddressOwner": addr},
                "coinType": coin_type,
                "amount": amount,
            })
        data["balanceChanges"] = balance_changes

    oc_blocks = _parse_kv_blocks(raw_output, "Object Changes")
    if oc_blocks:
        object_changes = []
        for block in oc_blocks:
            obj_id = block.get("ObjectID", "")
            sender = block.get("Sender", "")
            raw_owner = block.get("Owner", "")
            obj_type = block.get("ObjectType", "")
            owner_addr = _extract_table_address(raw_owner)
            object_changes.append({
                "objectId": obj_id,
                "sender": sender,
                "owner": {"AddressOwner": owner_addr},
                "objectType": obj_type,
            })
        data["objectChanges"] = object_changes

    return data if data else None


# =============================================================================
# Universal CLI Wrapper — Command Injection & Simulation
# =============================================================================

def _inject_flags(user_cmd):
    """
    Smart-inject --dry-run, --json, and --gas-budget into a Sui CLI command.
    Only adds flags that are not already present.
    """
    cmd = user_cmd.strip()

    if '--dry-run' not in cmd:
        cmd += ' --dry-run'
    if '--json' not in cmd:
        cmd += ' --json'
    if '--gas-budget' not in cmd:
        cmd += ' --gas-budget 20000000'

    return cmd


def _extract_sender(raw_output):
    """
    Extract the Sender address from Sui CLI dry-run output.

    The Sender line is always present in the Dry Run Transaction Data section:
      │ Sender: 0x8d2c81bce43d5c7c34ea9f6319a08d6ec69d4a45d3311616f3d2c5351a87d967 │

    Falls back to `sui client active-address` if not found.
    """
    match = re.search(r'Sender:\s*(0x[0-9a-fA-F]+)', raw_output)
    if match:
        return match.group(1)

    # Fallback: query the active address from the CLI
    try:
        result = subprocess.run(
            "sui client active-address 2>/dev/null",
            shell=True, capture_output=True, text=True, timeout=10
        )
        addr_match = re.search(r'(0x[0-9a-fA-F]+)', result.stdout)
        if addr_match:
            return addr_match.group(1)
    except Exception:
        pass

    return ""


def run_simulation(user_cmd):
    """
    Universal Sui CLI wrapper: inject --dry-run --json, execute the command,
    and return (structured_data, raw_output).

    Tries pipe-through-cat first (works on macOS), then TERM=dumb fallback.
    Attempts JSON parse; falls back to ASCII key-value block parser.
    """
    full_cmd = _inject_flags(user_cmd)

    attempts = [
        ("pipe through cat", f"{full_cmd} 2>/dev/null | cat"),
        ("TERM=dumb",        f"TERM=dumb {full_cmd} 2>/dev/null"),
    ]

    raw_output = ""

    for label, cmd in attempts:
        try:
            result = subprocess.run(
                cmd, shell=True, capture_output=True, text=True, timeout=30
            )
            output = result.stdout.strip()
            if not output:
                continue

            raw_output = output

            # Quick check: if the output looks like JSON, try to parse it
            trimmed = output.lstrip()
            if trimmed.startswith('{'):
                try:
                    return json.loads(trimmed), raw_output
                except json.JSONDecodeError:
                    pass

            # Got output — break and fall through to ASCII parser
            break

        except subprocess.TimeoutExpired:
            continue
        except Exception:
            continue

    # Primary path: parse the ASCII table output (this is what Sui 1.65.x emits)
    if raw_output:
        data = _build_structured_data(raw_output)
        return data, raw_output

    return None, ""


# =============================================================================
# Address Extraction Helpers
# =============================================================================

def _extract_address(owner_info):
    """
    Robustly extract an address string from any Sui owner representation.
    """
    if not owner_info:
        return ""
    if isinstance(owner_info, str):
        return owner_info.strip()
    if isinstance(owner_info, dict):
        return (
            owner_info.get("AddressOwner")
            or owner_info.get("ObjectOwner")
            or owner_info.get("address")
            or owner_info.get("owner")
            or ""
        ).strip()
    return ""


def _is_system_address(addr):
    """Return True if the address is a Sui system/framework/null address."""
    if not addr:
        return True
    a = addr.lower().strip()
    if re.match(r'^0x[0-9a-f]$', a):
        return True
    hex_body = a.replace("0x", "")
    if hex_body and all(c == '0' for c in hex_body):
        return True
    if a in ("shared", "immutable", ""):
        return True
    return False


def _normalize_addr(addr):
    """Lowercase + strip for consistent comparison."""
    return addr.lower().strip() if addr else ""


# =============================================================================
# Deep JSON Traversal — find balanceChanges / objectChanges at any depth
# =============================================================================

def _deep_find_key(data, target_keys):
    """
    Recursively search a nested dict/list for the first key in target_keys
    that maps to a non-empty list.
    """
    if isinstance(data, dict):
        for key in target_keys:
            val = data.get(key)
            if isinstance(val, list) and len(val) > 0:
                return val
        for v in data.values():
            found = _deep_find_key(v, target_keys)
            if found is not None:
                return found
    if isinstance(data, list):
        for item in data:
            found = _deep_find_key(item, target_keys)
            if found is not None:
                return found
    return None


# =============================================================================
# Core Audit Engine
# =============================================================================

def audit_transaction(data, expected_cost, victim_address):
    """
    Security audit: compare simulated dry-run results against user intent.

    Detection model (designed for real Sui CLI v1.65.x output):

      1. PRICE_MISMATCH — MORE THAN ONE non-victim address receives SUI.
         The largest recipient is the legitimate payee; extras are drains.

      2. HIJACK — An object ends up owned by an address that is NOT
         the victim and NOT the expected payment recipient.

    Returns:
        (is_safe: bool, alerts: list[dict], debug: dict)
    """
    alerts = []
    is_safe = True
    mist_per_sui = 1_000_000_000
    expected_mist = float(expected_cost) * mist_per_sui
    victim = _normalize_addr(victim_address)

    # =================================================================
    # 1. BALANCE CHANGES
    # =================================================================
    balance_changes = _deep_find_key(data, [
        "balanceChanges", "balance_changes", "BalanceChanges",
    ]) or []

    victim_total_loss = 0
    victim_total_gain = 0
    recipient_totals = {}

    for change in balance_changes:
        raw_owner = change.get("owner") or change.get("address") or ""
        addr = _normalize_addr(_extract_address(raw_owner))

        try:
            amount = int(change.get("amount", 0))
        except (ValueError, TypeError):
            try:
                amount = int(float(change.get("amount", 0)))
            except (ValueError, TypeError):
                continue

        if addr == victim:
            if amount < 0:
                victim_total_loss += abs(amount)
            else:
                victim_total_gain += amount
        elif amount > 0 and not _is_system_address(addr):
            recipient_totals[addr] = recipient_totals.get(addr, 0) + amount

    net_loss = victim_total_loss - victim_total_gain

    expected_recipient = ""
    suspicious_recipients = []

    if recipient_totals:
        sorted_recipients = sorted(
            recipient_totals.items(), key=lambda x: x[1], reverse=True
        )
        expected_recipient = sorted_recipients[0][0]
        suspicious_recipients = sorted_recipients[1:]

    for sus_addr, sus_amount in suspicious_recipients:
        is_safe = False
        alerts.append({
            "type": "PRICE_MISMATCH",
            "detail": (
                f"Hidden drain: {YELLOW}{sus_addr}{RESET} "
                f"received {RED}{sus_amount / mist_per_sui:.4f} SUI{RESET} "
                f"(not the primary payment recipient)"
            ),
        })

    # =================================================================
    # 2. OBJECT CHANGES — detect hijacking
    # =================================================================
    object_changes = _deep_find_key(data, [
        "objectChanges", "object_changes", "changed_objects", "ObjectChanges",
    ]) or []

    hijacked_count = 0

    for obj in object_changes:
        raw_owner = obj.get("owner") or obj.get("outputOwner") or {}
        dest = _normalize_addr(_extract_address(raw_owner))

        if not dest or dest == victim or _is_system_address(dest):
            continue

        if dest == expected_recipient:
            continue

        sender = _normalize_addr(
            obj.get("sender") or obj.get("Sender") or ""
        )
        is_victim_tx = (sender == victim or sender == "")

        if is_victim_tx:
            is_safe = False
            hijacked_count += 1
            obj_id = obj.get("objectId") or obj.get("ObjectID") or "unknown"
            obj_type = obj.get("objectType") or obj.get("ObjectType") or ""
            type_short = obj_type.split("::")[-1] if obj_type else ""
            alerts.append({
                "type": "HIJACK",
                "detail": (
                    f"Object {CYAN}{obj_id[:16]}...{RESET}"
                    + (f" ({type_short})" if type_short else "")
                    + f" diverted to {RED}{dest}{RESET}"
                ),
            })

    # =================================================================
    # Build debug info for display
    # =================================================================
    debug = {
        "victim_total_loss_mist": victim_total_loss,
        "victim_total_gain_mist": victim_total_gain,
        "net_loss_mist": net_loss,
        "expected_mist": expected_mist,
        "expected_recipient": expected_recipient,
        "suspicious_recipients": suspicious_recipients,
        "hijacked_count": hijacked_count,
        "balance_changes_count": len(balance_changes),
        "object_changes_count": len(object_changes),
    }

    return is_safe, alerts, debug


# =============================================================================
# Hackathon Demo-Ready Terminal Output
# =============================================================================

def print_banner():
    """Print the SuiSec ASCII banner."""
    banner = f"""
{BOLD}{CYAN}  ╔═══════════════════════════════════════════════════════════╗
  ║   ███████╗██╗   ██╗██╗███████╗███████╗ ██████╗          ║
  ║   ██╔════╝██║   ██║██║██╔════╝██╔════╝██╔════╝          ║
  ║   ███████╗██║   ██║██║███████╗█████╗  ██║               ║
  ║   ╚════██║██║   ██║██║╚════██║██╔══╝  ██║               ║
  ║   ███████║╚██████╔╝██║███████║███████╗╚██████╗          ║
  ║   ╚══════╝ ╚═════╝ ╚═╝╚══════╝╚══════╝ ╚═════╝          ║
  ║                                                           ║
  ║   {WHITE}Sui Transaction Security Auditor{CYAN}         v2.0.0   ║
  ║   {DIM}Pre-sign Dry-Run Defense for Sui Blockchain{RESET}{CYAN}          ║
  ╚═══════════════════════════════════════════════════════════╝{RESET}
"""
    print(banner)


def print_section(title, emoji=""):
    """Print a section divider."""
    line = "\u2500" * 55
    print(f"\n  {BOLD}{BLUE}{emoji} {title}{RESET}")
    print(f"  {DIM}{line}{RESET}")


def print_scan_status(phase, detail=""):
    """Print a scanning status line."""
    print(f"  {DIM}\u25B6 {phase}{RESET}" + (f" {DIM}{detail}{RESET}" if detail else ""))


def print_debug_table(debug, expected_cost):
    """Print debug balance info as a clean table."""
    m = 1_000_000_000
    loss = debug["victim_total_loss_mist"]
    gain = debug["victim_total_gain_mist"]
    net = debug["net_loss_mist"]
    exp = debug["expected_mist"]

    print_section("Balance Analysis", "\U0001F4B0")
    print(f"  {'Metric':<28} {'MIST':>18} {'SUI':>12}")
    print(f"  {DIM}{'\u2500' * 60}{RESET}")
    print(f"  {'Total SUI Out':<28} {YELLOW}{loss:>18,}{RESET} {YELLOW}{loss/m:>11.4f}{RESET}")
    print(f"  {'Total SUI Back':<28} {GREEN}{gain:>18,}{RESET} {GREEN}{gain/m:>11.4f}{RESET}")

    net_color = GREEN if net <= exp else (YELLOW if net <= exp * 1.5 else RED)
    print(f"  {BOLD}{'NET Loss':<28}{RESET} {net_color}{BOLD}{net:>18,}{RESET} {net_color}{BOLD}{net/m:>11.4f}{RESET}")
    print(f"  {'Expected Cost':<28} {DIM}{int(exp):>18,}{RESET} {DIM}{exp/m:>11.4f}{RESET}")

    er = debug.get("expected_recipient", "")
    if er:
        print(f"\n  {DIM}\u2192 Expected payee: {er[:20]}...{er[-8:]}{RESET}")

    if debug.get("suspicious_recipients"):
        print(f"\n  {RED}{BOLD}\u26A0  Suspicious Extra Recipients:{RESET}")
        for uaddr, uamt in debug["suspicious_recipients"]:
            print(f"    {RED}\u2192 {uaddr[:20]}...{uaddr[-8:]}  +{uamt/m:.4f} SUI{RESET}")


def print_comparison_table(debug, expected_cost, alerts):
    """
    Print a professional 'Intent vs. Simulated Reality' comparison table.
    This is the centrepiece of the hackathon demo.
    """
    m = 1_000_000_000
    net = debug["net_loss_mist"]
    exp = debug["expected_mist"]
    n_sus = len(debug.get("suspicious_recipients", []))
    n_hijack = debug.get("hijacked_count", 0)

    # Determine check results with color coding
    total_recipients = 1 + n_sus if debug.get("expected_recipient") else n_sus

    if n_sus == 0:
        recip_intent = f"{GREEN}1 (payee){RESET}"
        recip_result = f"{GREEN}{total_recipients} (payee only){RESET}"
    else:
        recip_intent = f"{GREEN}1 (payee){RESET}"
        recip_result = f"{RED}{total_recipients} \u26A0 EXTRA DRAIN{RESET}"

    if n_hijack == 0:
        hijack_intent = f"{GREEN}0{RESET}"
        hijack_result = f"{GREEN}0{RESET}"
    else:
        hijack_intent = f"{GREEN}0{RESET}"
        hijack_result = f"{RED}{n_hijack} \u26A0 HIJACKED{RESET}"

    cost_result_val = f"{net / m:.4f} SUI"
    if net <= exp * 1.5:
        cost_result = f"{GREEN}{cost_result_val}{RESET}"
    else:
        cost_result = f"{YELLOW}{cost_result_val} (*){RESET}"

    w1, w2, w3 = 22, 18, 24

    print_section("Intent vs. Simulated Reality", "\U0001F50E")
    print(f"  {BOLD}\u2554{'═' * w1}\u2566{'═' * w2}\u2566{'═' * w3}\u2557{RESET}")
    print(f"  {BOLD}\u2551 {'Check':<{w1-2}} \u2551 {'User Intent':<{w2-2}} \u2551 {'Simulation Result':<{w3-2}} \u2551{RESET}")
    print(f"  {BOLD}\u2560{'═' * w1}\u256C{'═' * w2}\u256C{'═' * w3}\u2563{RESET}")
    print(f"  \u2551 {'Max SUI Cost':<{w1-2}} \u2551 {GREEN}{expected_cost + ' SUI':<{w2 - 2}}{RESET} \u2551 {cost_result:<{w3 + 8}} \u2551")
    print(f"  \u2551 {'SUI Recipients':<{w1-2}} \u2551 {recip_intent:<{w2 + 8}} \u2551 {recip_result:<{w3 + 8}} \u2551")
    print(f"  \u2551 {'Objects Diverted':<{w1-2}} \u2551 {hijack_intent:<{w2 + 8}} \u2551 {hijack_result:<{w3 + 8}} \u2551")
    print(f"  {BOLD}\u255A{'═' * w1}\u2569{'═' * w2}\u2569{'═' * w3}\u255D{RESET}")

    if net > exp * 1.5:
        print(f"  {DIM}(*) NET Loss reflects entire Coin consumed by PTB.{RESET}")
        print(f"  {DIM}    See README Technical Notes: Sui Object-Centric Model.{RESET}")


def print_verdict(is_safe, alerts):
    """Print the final security verdict with visual impact."""
    if is_safe:
        print(f"\n  {BG_GREEN}{BOLD}{WHITE}"
              f"  \u2705  SAFE TO SIGN \u2014 Transaction matches declared intent.  "
              f"{RESET}\n")
    else:
        print(f"\n  {BG_RED}{BOLD}{WHITE}"
              f"  \U0001F6D1  BLOCKING MALICIOUS TRANSACTION  "
              f"{RESET}")

        print_section("Threat Details", "\u26A0\uFE0F")
        for alert in alerts:
            icon = "\U0001F4B8" if alert["type"] == "PRICE_MISMATCH" else "\U0001F3AF"
            tag_color = YELLOW if alert["type"] == "PRICE_MISMATCH" else MAGENTA
            print(f"  {icon} {tag_color}{BOLD}[{alert['type']}]{RESET} {alert['detail']}")

        print(f"\n  {BG_RED}{BOLD}{WHITE}"
              f"  \u274C  DO NOT SIGN \u2014 This transaction will steal your assets.  "
              f"{RESET}\n")


# =============================================================================
# Main Entry Point — Universal CLI Wrapper
# =============================================================================

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print_banner()
        print(f"  {BOLD}Usage:{RESET}")
        print(f"    python3 main.py {YELLOW}<expected_sui>{RESET} {CYAN}'<full_sui_command>'{RESET}")
        print()
        print(f"  {BOLD}Example:{RESET}")
        print(f"    python3 main.py 0.01 'sui client ptb \\")
        print(f"      --move-call 0xPKG::module::function @0xCOIN @0xNFT \\")
        print(f"      --gas-budget 20000000'")
        print()
        print(f"  {DIM}SuiSec will auto-inject --dry-run and --json, simulate the{RESET}")
        print(f"  {DIM}transaction, detect the sender, and audit the results.{RESET}\n")
        sys.exit(1)

    sui_intent = sys.argv[1]
    user_cmd = sys.argv[2]

    # Validate expected cost
    try:
        float(sui_intent)
    except ValueError:
        print(f"{RED}Error: '{sui_intent}' is not a valid SUI amount.{RESET}")
        sys.exit(1)

    print_banner()

    # --- Phase 1: Simulation ---
    print_section("Transaction Simulation", "\U0001F50D")
    print_scan_status("Command intercepted")
    print_scan_status("Injecting --dry-run --json flags...")
    print_scan_status("Expected cost", f"{YELLOW}{sui_intent} SUI{RESET}")

    simulation, raw_output = run_simulation(user_cmd)

    if not simulation:
        print(f"\n  {RED}{BOLD}\u274C  Could not parse dry-run output from Sui CLI.{RESET}")
        print(f"  {DIM}Possible causes:{RESET}")
        print(f"  {DIM}  - Your address does not own the specified objects{RESET}")
        print(f"  {DIM}  - The command syntax is invalid{RESET}")
        print(f"  {DIM}  - Sui CLI version incompatibility (tested: v1.65.x){RESET}\n")
        sys.exit(1)

    # --- Phase 2: Sender Detection ---
    sender = _extract_sender(raw_output)
    if not sender:
        print(f"\n  {RED}{BOLD}\u274C  Could not detect sender address.{RESET}")
        print(f"  {DIM}Run 'sui client active-address' to verify your wallet.{RESET}\n")
        sys.exit(1)

    print_scan_status("Sender detected", f"{CYAN}{sender[:16]}...{sender[-8:]}{RESET}")
    print_scan_status("Dry-run data captured", f"{GREEN}OK{RESET}")

    # --- Phase 3: Security Audit ---
    print_scan_status("Running security audit...")

    safe, reports, debug = audit_transaction(simulation, sui_intent, sender)

    # --- Phase 4: Results ---
    print_comparison_table(debug, sui_intent, reports)
    print_debug_table(debug, sui_intent)
    print_verdict(safe, reports)

    # Exit code: 0 = safe, 1 = malicious
    sys.exit(0 if safe else 1)
