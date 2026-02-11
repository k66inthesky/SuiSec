#!/bin/bash
# =============================================================================
# SuiSec Integration Test Script — Universal CLI Wrapper Mode
# Tests three scenarios: safe purchase, hidden overspend, and object hijacking.
# Designed for Hackathon demo — each scenario runs independently (no set -e).
# =============================================================================

# ---------------------------------------------------------------------------
# 1. Environment Config (replace with your own testnet wallet objects)
# ---------------------------------------------------------------------------
PKG="0x76a28891c190e3065ee0c9f7377ea64b10a1a7a3073ee4fcb8354911d51bfdf7"
NFT="0x1af4c39b389374caebb8d5fc7cb86dc702d7b97c49a390e41f5a8c4574b56ba4"
PROFILE="0x7ebf760f853d8c7453166cb137463ca90198277b437b11b6844ef3d91449e06c"
COIN="0x94bbc4f8e2a3f8b446a81fb735df6c38070293cd7aaed3b6689815b5668b878b"

BOLD="\033[1m"
DIM="\033[2m"
CYAN="\033[96m"
YELLOW="\033[93m"
RED="\033[91m"
GREEN="\033[92m"
RESET="\033[0m"

divider() {
    echo -e "\n${DIM}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}\n"
}

# ---------------------------------------------------------------------------
# 2. Scenario 1: Safe NFT Purchase (should PASS — SAFE TO SIGN)
#    Sender address is auto-detected from dry-run output.
# ---------------------------------------------------------------------------
divider
echo -e "${BOLD}${GREEN}  🧪 TEST 1/3: Safe NFT Purchase${RESET}"
echo -e "${DIM}  Expected: ✅ SAFE TO SIGN${RESET}\n"
python3 main.py 0.01 \
  "sui client ptb --move-call $PKG::suisec_test::safe_buy @$COIN @$NFT --gas-budget 20000000"
echo -e "${DIM}  Exit code: $?${RESET}"

# ---------------------------------------------------------------------------
# 3. Scenario 2: Hidden SUI Stealing (should FAIL — BLOCKING)
# ---------------------------------------------------------------------------
divider
echo -e "${BOLD}${YELLOW}  🧪 TEST 2/3: Hidden SUI Stealing (0.1 SUI drained)${RESET}"
echo -e "${DIM}  Expected: 🛑 BLOCKING (PRICE_MISMATCH)${RESET}\n"
python3 main.py 0.01 \
  "sui client ptb --move-call $PKG::suisec_test::hidden_steal @$COIN @$NFT --gas-budget 20000000"
echo -e "${DIM}  Exit code: $?${RESET}"

# ---------------------------------------------------------------------------
# 4. Scenario 3: Profile Asset Hijacking (should FAIL — BLOCKING)
# ---------------------------------------------------------------------------
divider
echo -e "${BOLD}${RED}  🧪 TEST 3/3: Profile Asset Hijacking${RESET}"
echo -e "${DIM}  Expected: 🛑 BLOCKING (HIJACK)${RESET}\n"
python3 main.py 0.01 \
  "sui client ptb --move-call $PKG::suisec_test::profile_theft @$COIN @$NFT @$PROFILE --gas-budget 20000000"
echo -e "${DIM}  Exit code: $?${RESET}"

# ---------------------------------------------------------------------------
# 5. Summary
# ---------------------------------------------------------------------------
divider
echo -e "${BOLD}${CYAN}  ✅ All 3 scenarios executed. Review results above.${RESET}\n"
