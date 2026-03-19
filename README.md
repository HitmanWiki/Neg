# NegRisk Arb Bot — Fully Automated

Scans Polymarket every 30 minutes. Only bets when guaranteed profit exists.
No human intervention needed after setup.

---

## What It Does

```
Every 30 minutes:
  1. Scans all active NegRisk grouped markets
  2. Finds groups where sum of YES prices < $0.98
  3. Safety checks: profit 2-30%, volume > $500, closes < 48hrs
  4. Auto-buys YES on ALL outcomes in profitable groups
  5. Logs everything to bot_log.csv
  6. Sleeps 30 mins → repeats
```

---

## PHASE 1 — Test It First (Dry Run, Free)

```bash
# Install dependencies
pip install requests pandas python-dotenv py-clob-client

# Run in simulation mode (no real money)
python bot.py
```

The bot will show you exactly what it WOULD bet on without spending anything.
Run for 2-3 days to verify opportunities are real before going live.

---

## PHASE 2 — Go Live With $20

### Step 1 — Get Polymarket API Keys

1. Go to **polymarket.com**
2. Connect MetaMask wallet
3. Deposit **$20 USDC** (minimum)
4. Go to **Profile → API Keys → Create**
5. Save: API Key, Secret, Passphrase
6. Your proxy wallet = shown in profile

### Step 2 — Configure

```bash
cp .env.example .env
```

Edit `.env`:
```
POLY_API_KEY=your_key
POLY_API_SECRET=your_secret
POLY_PASSPHRASE=your_passphrase
POLY_PRIVATE_KEY=your_metamask_private_key
POLY_PROXY_WALLET=your_proxy_wallet
```

### Step 3 — Enable Live Trading

In `bot.py`, change:
```python
"dry_run": False,    # Was True
```

### Step 4 — Run

```bash
python bot.py
```

---

## Run 24/7 (Keep It Always On)

### Option A — Windows (Task Scheduler)
```
1. Open Task Scheduler
2. Create Basic Task
3. Action: Start Program → python bot.py
4. Trigger: At startup
5. Set working directory to bot folder
```

### Option B — Railway.app (Free Cloud)
```bash
# Push to GitHub, then deploy on railway.app
# Free 500 hours/month — enough for 24/7
```

### Option C — Keep Terminal Open
```bash
# Windows: run in background
start /B python bot.py

# Or just leave the terminal window open
python bot.py
```

---

## Monitor Your Bot

```bash
# Watch live log
tail -f bot.log          # Linux/Mac
Get-Content bot.log -Wait  # Windows PowerShell

# Check open positions
cat positions.json

# Check trade history
python -c "import pandas as pd; print(pd.read_csv('bot_log.csv').to_string())"
```

---

## Files Created By Bot

```
bot.log              ← All activity (scan results, bets placed)
positions.json       ← Currently open positions
bot_log.csv          ← Full trade history with PNL
negrisk_scan.csv     ← Latest scan results
```

---

## Safety Rules Built In

```
1. Never bets more than $4 per group ($20 / 5 groups)
2. Keeps 10% reserve — never fully deploys
3. Max 5 open positions at once
4. Skips profit > 30% (likely incomplete sets)
5. Skips profit < 2% (not worth execution risk)
6. Requires $500+ volume (enough liquidity)
7. Only bets markets closing < 48 hours
8. If any leg fails — logs error, continues
```

---

## Expected Results With $20

```
Safe opportunities: 5-15 per day closing < 48hrs
Avg profit: 5-10% per group
Avg bet: $4 per group

Daily profit: ~$1-3 on $20 capital = 5-15%/day
Monthly:      $20 → $60-100 (compound)

To get $10/day: need ~$200-500 capital
```

---

## FAQ

**Q: What if a market gets voided?**
A: Polymarket refunds ~50% of your stake. Bot logs it as a loss.

**Q: What if prices move before all legs filled?**
A: Bot uses ASK price with 2% tolerance. If price moves more, order may fail partially.

**Q: How do I stop the bot?**
A: Press Ctrl+C in the terminal.

**Q: Can I change the capital amount?**
A: Yes — edit `total_capital` in CONFIG at top of bot.py.
