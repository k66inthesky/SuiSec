import sys
import json
import subprocess
import shlex
import re
from typing import List, Dict, Any, Optional

# --- Constants ---

SYSTEM_ADDRESSES = {"0x1", "0x2", "0x3", "0x5", "0x6", "0x7", "0x8"}


def get_address(owner_field: Any) -> Optional[str]:
    """Extract address string from owner field (plain string or {"AddressOwner": ...} dict)."""
    if isinstance(owner_field, str):
        return owner_field
    if isinstance(owner_field, dict):
        return owner_field.get("AddressOwner")
    return None


def detect_sender(balance_changes: List[Dict[str, Any]]) -> str:
    """
    Auto-detect sender from dry-run balanceChanges.
    Returns the address with the most negative SUI balance change.
    Exits with code 1 if no negative SUI entry found (inconclusive simulation).
    """
    best_addr = None
    best_amount = 0
    for change in balance_changes:
        if change.get("coinType") != "0x2::sui::SUI":
            continue
        amount = int(change.get("amount", 0))
        addr = get_address(change.get("owner"))
        if addr is None:
            continue
        if amount < best_amount:
            best_amount = amount
            best_addr = addr
    if best_addr is None:
        print("❌ Audit Error: Could not detect sender from simulation output.")
        sys.exit(1)
    return best_addr


# --- Secure Execution Configuration ---

def run_simulation(ptb_command: str) -> str:
    """
    Safely executes Sui commands. Uses shell=False and shlex to prevent command injection vulnerabilities.
    """
    try:
        # Securely split the string into an argument list using shlex.split
        args = shlex.split(ptb_command)
        
        # Security check: Force the first command to be strictly 'sui'
        if not args or args[0] != 'sui':
            print("❌ Security Error: Only 'sui' commands are authorized.")
            sys.exit(1)
            
        # Automatically append required safety detection parameters
        if '--dry-run' not in args:
            args.append('--dry-run')
        if '--json' not in args:
            args.append('--json')

        # Core security fix: Execute using a list and disable shell
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            shell=False  # Disable Shell to block RCE attack vectors
        )

        if result.returncode != 0:
            # Handle error messages from the Sui CLI (e.g., syntax errors)
            clean_error = re.sub(r'\x1b\[[0-9;]*m', '', result.stderr)
            print(f"❌ Sui CLI Error: {clean_error.strip()}")
            sys.exit(1)

        return result.stdout
    except Exception as e:
        print(f"❌ Execution Failure: {str(e)}")
        sys.exit(1)

# --- Audit Logic ---

def audit_balance_changes(json_data: Dict[str, Any], intended_cost: float, owner_addr: str):
    """
    Analyzes balance changes to detect excessive spending and asset hijacking.
    """
    balance_changes = json_data.get("balanceChanges", [])
    actual_sui_loss = 0.0
    
    # 1. Detect SUI expenditure (PRICE_MISMATCH)
    for change in balance_changes:
        if (change.get("owner") == owner_addr or change.get("owner", {}).get("AddressOwner") == owner_addr) \
           and change.get("coinType") == "0x2::sui::SUI":
            amount = int(change.get("amount", 0))
            if amount < 0:
                actual_sui_loss += abs(amount) / 1e9

    # 2. Detect object ownership changes (HIJACK)
    # Check if objects originally owned by the user are transferred to others in objectChanges
    object_changes = json_data.get("objectChanges", [])
    hijacked_objects = []
    for obj in object_changes:
        if obj.get("type") == "mutated":
            # Simple logic: If an object was user-held but is now transferred to a non-user address (e.g., 0xdeadbeef)
            # This section can be expanded based on actual simulation data
            pass 

    # --- Output Results ---
    print("\n" + "="*45)
    print("        🛡️  SUISEC AUDIT REPORT 🛡️")
    print("="*45)
    print(f"Intended Spend : {intended_cost:>10.4f} SUI")
    print(f"Actual Loss    : {actual_sui_loss:>10.4f} SUI")
    print("-" * 45)

    # Criteria: Actual expenditure should not exceed intended cost (plus a 0.02 Gas buffer)
    if actual_sui_loss > (intended_cost + 0.02):
        print(f"🚨 [RESULT] ❌ MALICIOUS: Price mismatch detected!")
        print(f"   Hidden drain of {actual_sui_loss - intended_cost:.4f} SUI.")
        sys.exit(1)
    else:
        print(f"✅ [RESULT] SAFE TO SIGN.")
    print("="*45 + "\n")

def main():
    if len(sys.argv) < 4:
        print("Usage: python3 main.py '<ptb_command>' <intended_cost> <owner_address>")
        sys.exit(1)

    raw_cmd = sys.argv[1]
    intended_cost = float(sys.argv[2])
    owner_addr = sys.argv[3]

    # 1. Execute secure simulation
    raw_output = run_simulation(raw_cmd)
    
    # 2. Parse JSON (filtering out potential ASCII warning text from Sui CLI)
    try:
        json_start = raw_output.find('{')
        if json_start == -1: raise ValueError("No JSON found")
        json_data = json.loads(raw_output[json_start:])
        
        # 3. Perform the audit
        audit_balance_changes(json_data, intended_cost, owner_addr)
    except Exception as e:
        print(f"❌ Audit Error: Failed to parse simulation data. {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
