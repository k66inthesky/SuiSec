<div align="center">

# SuiSec 🛡️🦞💧
<img width="128" height="128" alt="SuiSec128x128" src="https://github.com/user-attachments/assets/4d208dc0-e078-4e91-aedc-ea1419dee3c7" />

**A security extension for OpenClaw's Sui client call and PTB dry-run capabilities**

</div>


SuiSec is an OpenClaw extension that performs intent analysis on every Sui transaction before execution. By leveraging `sui client call --dry-run` and `sui client ptb --dry-run`, SuiSec compares the simulated transaction results against the user's declared intent to detect malicious contract behavior and prevent asset theft.

## Overview

As powerful AI agents like OpenClaw bring unprecedented convenience to blockchain interactions, they also introduce the risk of executing malicious contracts. SuiSec acts as a security gatekeeper, ensuring that every transaction matches the user's intent before signing.

**Key Features:**
- 🔍 Automated intent analysis using Sui's dry-run functionality
- 🚨 Detects hidden SUI drains and object hijacking
- ✅ Basic malicious contract filtering for OpenClaw transactions
- 🧪 Tested with testnet malicious contracts (`safe_buy`, `hidden_steal`, `profile_theft`)

## How It Works

The core intent analysis logic is implemented in `main.py`, with agent integration guidelines in `SKILL.md`. When OpenClaw processes a Sui transaction:

1. **Pre-execution audit**: SuiSec intercepts the command and injects `--dry-run` flags
2. **Intent comparison**: Parses balance changes and object changes from simulation
3. **Threat detection**: Identifies price mismatches and ownership hijacking
4. **Decision**: Returns exit code `0` (safe) or `1` (malicious) to block or allow execution

## Quick Start

### Installation

+ Install from ClawHub
  
  Goto https://clawhub.ai/skills search suisec or
  just jump into https://clawhub.ai/k66inthesky/suisec

  ```
  npx clawhub install suisec
  ```
  or
  ```
  openclaw skills install k66inthesky/suisec
  ```

+ Locol Install
  ```bash
  # Clone the repository
  git clone https://github.com/yourusername/suisec.git
  cd suisec
  
  # Run setup (installs Sui CLI if needed)
  ./setup.sh
  ```

### Usage

+ Example Prompt1 for OpenClaw
  ```bash
  I want to buy the FakeNFT from this contract: 0x76a28891c190e3065ee0c9f7377ea64b10a1a7a3073ee4fcb8354911d51bfdf7. The price is 0.01 SUI. Run the SuiSec audit first—if the result is SAFE, just go ahead and execute the transaction for me.
  ```

+ Example Prompt2 for OpenClaw
  ```
  I found another NFT on sale at the same contract address. It's also 0.01 SUI, but this one uses the hidden_steal function. Audit it first, and only execute if it's safe.
  ```

**Execution Logic:**
| Output | Exit Code | Action |
|--------|-----------|--------|
| `SAFE TO SIGN` | `0` | ✅ Transaction matches intent - proceed |
| `BLOCKING MALICIOUS TRANSACTION` | `1` | 🛑 Threats detected - do not execute |

## Testing

A minimal test suite is included for convenience:

```bash
./test_suisec.sh
```

**Note:** The test script uses testnet contracts and may require updates. Please modify the contract addresses in the script to match your testnet deployment.

The test suite covers three scenarios:
1. ✅ **Safe Purchase** - Legitimate NFT buy with correct pricing
2. 🚨 **Hidden Steal** - Contract secretly drains extra SUI
3. 🚨 **Profile Theft** - Contract hijacks user objects

## Threat Detection

### Automated Detection (main.py v2.0.0)

| Threat Type | Detection Method |
|------------|-----------------|
| **PRICE_MISMATCH** | Multiple non-system addresses receive SUI; extras flagged as hidden drains |
| **HIJACK** | Objects diverted to addresses other than sender or intended recipient |

### Example Output

```
🛑 SuiSec BLOCKING MALICIOUS TRANSACTION

Threats detected:
- [PRICE_MISMATCH] Hidden drain: 0x...deadbeef received 0.1000 SUI
- [HIJACK] Object 0x7ebf... (UserProfile) diverted to 0x...deadbeef

❌ DO NOT SIGN — This transaction will steal your assets.
```

## OpenClaw Integration

SuiSec is designed as an OpenClaw skill. See `SKILL.md` for full integration guidelines. In brief:

1. OpenClaw intercepts Sui transaction requests
2. Runs `python3 main.py <expected_cost> '<command>'` before execution
3. Checks exit code: proceed on `0`, block on `1`
4. Displays threat analysis if malicious behavior detected

## Limitations

⚠️ **SuiSec provides basic intent analysis only.** It can detect common malicious patterns like hidden transfers and object hijacking, but sophisticated attacks may evade detection. Always verify contracts from untrusted sources.

Supported detection:
- ✅ Hidden SUI drains to unexpected addresses
- ✅ Object ownership hijacking
- ✅ Basic asset flow mismatches

Not yet detected:
- ❌ Advanced proxy call patterns
- ❌ Time-delayed malicious logic
- ❌ Complex multi-step exploits

## A Personal Reflection

Powerful AI agents like OpenClaw bring incredible convenience to Web3, but they also carry the hidden risk of executing malicious contracts on our behalf. I find Sui's dry-run functionality fascinating—it provides a window into what a transaction *would* do before committing on-chain.

I plan to continue exploring what intent analysis can achieve in detecting and preventing malicious contract interactions. Updates will be shared here on this GitHub repository and on [ClawHub](https://clawhub.ai/). If you have ideas or suggestions for improving SuiSec, please feel free to open an issue or contribute.

Lastly, I'm **k66**, and also a co-founder of [**SuiAudit**](https://github.com/suigurad). I invite you to follow SuiAudit's development as we work to make the Sui ecosystem safer for everyone.

## Contributing

Contributions are welcome! Please feel free to submit issues or pull requests.

## License

MIT License - see LICENSE file for details

---

**Disclaimer:** SuiSec is an experimental security tool. While it provides basic protection against common attack patterns, it cannot guarantee complete security. Always exercise caution when interacting with unverified smart contracts.
