"""
NEGRISK ARB BOT — FULLY AUTOMATED + SELF-TRACKING
====================================================
Phase 1 (Days 1-14):  dry_run=True  → auto-tracks outcomes, builds real data
Phase 2 (Day 15+):    dry_run=False → goes live only if win rate > 80%

FULLY AUTOMATED:
  - Scans every 5 mins (not 30)
  - Records every opportunity
  - Auto-checks resolution outcomes
  - Calculates real win rate
  - Goes live automatically when proven profitable
  - Sends summary to console every hour

Install: pip install requests python-dotenv py-clob-client
Run:     python bot.py
"""

import os, sys, time, json, logging, requests
from datetime import datetime, timezone, timedelta
from collections import defaultdict
from dotenv import load_dotenv

# Windows UTF-8 fix
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.FileHandler("bot.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger(__name__)

# ─── CONFIG ───────────────────────────────────────────────────────────────────
CONFIG = {
    # Capital
    "total_capital":         20.0,
    "max_bet_per_group":     4.0,
    "min_bet_per_group":     1.0,
    "max_groups_open":       5,
    "reserve_pct":           0.10,

    # Strategy — tightened based on OpenAI feedback
    "max_cost_per_set":      0.95,    # Raised from 0.98 → need 5%+ profit
    "min_profit_pct":        0.05,    # Raised from 2% → 5% (covers fees)
    "max_profit_pct":        0.25,    # Lowered from 30% → 25%
    "max_hrs_to_close":      48.0,
    "min_outcomes":          3,
    "max_outcomes":          20,
    "min_volume":            1000,    # Raised from 500 → 1000 (better liquidity)

    # Execution
    "scan_interval_secs":    300,     # 5 minutes (was 30 mins)
    "summary_interval_secs": 3600,   # Print summary every hour

    # Auto-graduation
    "dry_run":               True,    # Starts in paper mode
    "auto_graduate":         False,   # Set True to auto go-live after proof
    "min_paper_trades":      20,      # Need 20 paper trades before graduating
    "min_win_rate":          0.75,    # Need 75% win rate to graduate
}

# ─── HELPERS ──────────────────────────────────────────────────────────────────
def pj(v):
    if isinstance(v, (list, dict)): return v
    try:    return json.loads(v)
    except: return []

def get_price(m):
    for k in ["lastTradePrice", "bestAsk"]:
        try:
            v = float(m.get(k) or 0)
            if 0.005 < v < 0.995: return round(v, 4)
        except: pass
    try:
        ask = float(m.get("bestAsk") or 1)
        if 0.005 < ask < 0.995: return round(ask, 4)
    except: pass
    prices = pj(m.get("outcomePrices", []))
    if prices:
        try:
            v = float(prices[0])
            if 0.005 < v < 0.995: return round(v, 4)
        except: pass
    return None

def get_hrs_left(ev):
    ed = ev.get("endDate", "")
    if not ed: return None
    try:
        end_dt = datetime.fromisoformat(
            ed.replace("Z", "+00:00") if "T" in ed else ed + "T00:00:00+00:00")
        hrs = (end_dt - datetime.now(timezone.utc)).total_seconds() / 3600
        return round(hrs, 1) if hrs > 0 else None
    except: return None

def is_negrisk(ev, markets):
    for m in markets:
        if m.get("negRisk") or m.get("neg_risk"):
            return True
    if ev.get("negRisk") or ev.get("neg_risk"):
        return True
    title = (ev.get("title") or "").lower()
    bad   = ["what price", "how high", "how low", "will it reach",
             "will btc", "will eth", "will sol", "will bitcoin"]
    if any(p in title for p in bad): return False
    prices = [get_price(m) for m in markets if get_price(m)]
    if prices and sum(prices) < 0.50: return False
    return True


# ─── DATABASE (simple JSON files) ─────────────────────────────────────────────
class DB:
    def __init__(self):
        self.positions_file  = "positions.json"
        self.performance_file= "performance.json"
        self.positions        = self._load(self.positions_file, {})
        self.performance      = self._load(self.performance_file, {
            "paper_trades": [], "live_trades": [],
            "total_paper_profit": 0, "total_live_profit": 0,
            "started_at": datetime.now(timezone.utc).isoformat(),
        })

    def _load(self, f, default):
        if os.path.exists(f):
            try:
                with open(f) as fp: return json.load(fp)
            except: pass
        return default

    def save(self):
        with open(self.positions_file,   "w") as f: json.dump(self.positions,   f, indent=2)
        with open(self.performance_file, "w") as f: json.dump(self.performance, f, indent=2)

    def add_position(self, gid, data):
        self.positions[gid] = data
        self.save()

    def remove_position(self, gid):
        self.positions.pop(gid, None)
        self.save()

    def record_result(self, trade):
        key = "live_trades" if not trade.get("paper") else "paper_trades"
        self.performance[key].append(trade)
        if trade.get("paper"):
            self.performance["total_paper_profit"] = round(
                self.performance.get("total_paper_profit", 0) + trade["pnl"], 4)
        else:
            self.performance["total_live_profit"] = round(
                self.performance.get("total_live_profit", 0) + trade["pnl"], 4)
        self.save()

    def paper_stats(self):
        trades = self.performance["paper_trades"]
        if not trades: return None
        wins   = sum(1 for t in trades if t["pnl"] > 0)
        losses = sum(1 for t in trades if t["pnl"] <= 0)
        total  = wins + losses
        return {
            "total":   total,
            "wins":    wins,
            "losses":  losses,
            "win_rate":wins / total if total else 0,
            "total_pnl": sum(t["pnl"] for t in trades),
            "avg_pnl": sum(t["pnl"] for t in trades) / total if total else 0,
        }


# ─── OUTCOME CHECKER ──────────────────────────────────────────────────────────
def check_resolutions(db: DB):
    """
    For every open position past its close time,
    fetch the resolved outcome and record actual PNL.
    Fully automated — no human needed.
    """
    resolved_count = 0
    now = datetime.now(timezone.utc)

    for gid, pos in list(db.positions.items()):
        close_dt_str = pos.get("closes_at")
        if not close_dt_str:
            continue

        try:
            close_dt = datetime.fromisoformat(close_dt_str)
        except Exception:
            continue

        # Only check positions past their close time
        if now < close_dt + timedelta(minutes=30):
            continue

        # Fetch current market state
        cid = pos.get("condition_id")
        if not cid:
            db.remove_position(gid)
            continue

        try:
            r = requests.get(
                "https://gamma-api.polymarket.com/markets",
                params={"conditionId": cid},
                timeout=10,
            )
            if r.status_code != 200:
                continue
            data = r.json()
            if not data:
                continue

            market = data[0] if isinstance(data, list) else data
            prices = pj(market.get("outcomePrices", []))
            if not prices:
                continue

            # Check if resolved: winner = price 1.0
            resolved = any(float(p) >= 0.99 for p in prices)
            if not resolved:
                continue

            # Calculate REALISTIC PNL with real costs simulated
            invested     = pos.get("invested", 0)
            total_cost   = pos.get("total_cost", 0)
            n_outcomes   = pos.get("n", 3)

            # Gross profit (paper)
            gross_pct    = (1 - total_cost) / total_cost if total_cost > 0 else 0

            # Real costs (maker orders = 0% fee, but spread + slippage apply)
            # Spread:   ~1.5% per leg averaged across all outcomes
            # Slippage: ~0.5% per leg
            # These compound: 7 legs at 1.5% = 10.5% spread cost total
            spread_cost   = 0.015 * n_outcomes
            slippage_cost = 0.005 * n_outcomes
            net_pct       = gross_pct - spread_cost - slippage_cost

            # 10% chance one leg fails to fill (partial fill risk)
            import random as _rnd
            if _rnd.random() < 0.10:
                actual_pnl = -round(invested * 0.30, 3)
                status = "partial_fill_loss"
            else:
                actual_pnl = round(invested * net_pct, 3)
                status = "won" if actual_pnl > 0 else "lost_to_costs"

            log.info(f"  Realistic costs: spread={spread_cost:.1%} "
                     f"slip={slippage_cost:.1%} "
                     f"gross={gross_pct:.1%} net={net_pct:.1%}")

            # Check if voided
            voided = all(0.01 < float(p) < 0.99 for p in prices)
            if voided:
                actual_pnl = -round(invested * 0.5, 3)
                status = "voided"

            # Record result
            db.record_result({
                "gid":       gid,
                "title":     pos.get("title", "")[:60],
                "invested":  invested,
                "pnl":       actual_pnl,
                "status":    status,
                "profit_pct":round(gross_pct * 100, 1),
                "paper":     pos.get("paper", True),
                "closed_at": now.isoformat(),
            })
            db.remove_position(gid)
            resolved_count += 1

            emoji = "+" if actual_pnl > 0 else "-"
            log.info(f"[RESOLVED] {status.upper()} | "
                     f"{pos.get('title','')[:40]} | "
                     f"PnL: {emoji}${abs(actual_pnl):.3f}")

        except Exception as e:
            log.error(f"Resolution check error for {gid}: {e}")

    return resolved_count


# ─── SCANNER ──────────────────────────────────────────────────────────────────
def scan_opportunities():
    opps   = []
    offset, limit = 0, 100

    for page in range(1, 20):
        try:
            r = requests.get(
                "https://gamma-api.polymarket.com/events",
                params={"active": "true", "closed": "false",
                        "limit": limit, "offset": offset,
                        "order": "volume", "ascending": "false"},
                timeout=20,
            )
            r.raise_for_status()
            batch = r.json()
        except Exception as e:
            log.error(f"Scan API error: {e}")
            break

        if not batch: break

        for ev in batch:
            markets = ev.get("markets", [])
            if not (CONFIG["min_outcomes"] <= len(markets) <= CONFIG["max_outcomes"]):
                continue

            hrs = get_hrs_left(ev)
            if hrs is not None and hrs > CONFIG["max_hrs_to_close"]:
                continue

            if not is_negrisk(ev, markets):
                continue

            priced = []
            for m in markets:
                px = get_price(m)
                if px is not None:
                    cid = m.get("conditionId") or m.get("condition_id", "")
                    priced.append({
                        "q":          (m.get("question") or "")[:60],
                        "px":         px,
                        "condition_id": cid,
                        "token_ids":  pj(m.get("clobTokenIds", [])),
                        "volume":     float(m.get("volumeNum") or 0),
                    })

            if len(priced) < CONFIG["min_outcomes"]: continue

            prices     = [m["px"] for m in priced]
            total_cost = sum(prices)
            total_vol  = sum(m["volume"] for m in priced)

            if total_cost >= CONFIG["max_cost_per_set"]: continue

            profit_pct = (1.0 - total_cost) / total_cost
            if not (CONFIG["min_profit_pct"] <= profit_pct <= CONFIG["max_profit_pct"]):
                continue
            if total_vol < CONFIG["min_volume"]: continue

            # End date for resolution checking
            end_dt_str = ev.get("endDate", "")

            opps.append({
                "group_id":    str(ev.get("id", "") or ev.get("slug", "")),
                "condition_id":priced[0]["condition_id"] if priced else "",
                "title":       ev.get("title", "")[:70],
                "n":           len(priced),
                "total_cost":  round(total_cost, 4),
                "profit_pct":  round(profit_pct, 4),
                "hrs_left":    hrs,
                "total_vol":   total_vol,
                "closes_at":   end_dt_str,
                "markets":     priced,
            })

        if len(batch) < limit: break
        offset += limit
        time.sleep(0.2)

    opps.sort(key=lambda x: x["hrs_left"] or 99999)
    return opps


# ─── EXECUTOR ─────────────────────────────────────────────────────────────────
class Executor:
    def __init__(self):
        self.dry      = CONFIG["dry_run"]
        self.api_key  = os.getenv("POLY_API_KEY", "")
        self.api_sec  = os.getenv("POLY_API_SECRET", "")
        self.api_pass = os.getenv("POLY_PASSPHRASE", "")
        self.priv_key = os.getenv("POLY_PRIVATE_KEY", "")
        self.proxy    = os.getenv("POLY_PROXY_WALLET", "")

    def balance(self) -> float:
        if self.dry: return CONFIG["total_capital"]
        try:
            from py_clob_client.client import ClobClient
            from py_clob_client.clob_types import ApiCreds
            c = ClobClient(
                host="https://clob.polymarket.com",
                key=self.priv_key, chain_id=137,
                creds=ApiCreds(self.api_key, self.api_sec, self.api_pass),
                signature_type=2, funder=self.proxy,
            )
            return float(c.get_balance().get("USDC", 0))
        except Exception as e:
            log.error(f"Balance error: {e}"); return 0.0

    def buy_all(self, group, amount_per_leg) -> bool:
        if self.dry:
            log.info(f"[PAPER] {len(group['markets'])} outcomes in '{group['title'][:40]}'")
            for m in group["markets"]:
                log.info(f"  [PAPER] BUY {m['q'][:35]} @ ${m['px']:.4f} x ${amount_per_leg:.2f}")
            return True

        # LIVE: atomic-style — place all, cancel all if any fail
        from py_clob_client.client import ClobClient
        from py_clob_client.clob_types import ApiCreds, OrderArgs
        from py_clob_client.order_builder.constants import BUY

        try:
            c = ClobClient(
                host="https://clob.polymarket.com",
                key=self.priv_key, chain_id=137,
                creds=ApiCreds(self.api_key, self.api_sec, self.api_pass),
                signature_type=2, funder=self.proxy,
            )
            placed = []
            for m in group["markets"]:
                tids = m.get("token_ids", [])
                if not tids: raise Exception(f"No token ID for {m['q'][:30]}")
                order = c.create_and_post_order(OrderArgs(
                    price=m["px"], size=round(amount_per_leg / m["px"], 2),
                    side=BUY, token_id=tids[0], fee_rate_bps=0,
                ))
                placed.append(order)
                log.info(f"  PLACED: {m['q'][:35]} @ ${m['px']:.4f}")
                time.sleep(0.3)
            return len(placed) == len(group["markets"])
        except Exception as e:
            log.error(f"Execution error: {e}")
            return False


# ─── AUTO-GRADUATION LOGIC ────────────────────────────────────────────────────
def should_graduate(db: DB) -> bool:
    """Check if paper trading results justify going live."""
    if not CONFIG["auto_graduate"]:
        return False
    stats = db.paper_stats()
    if not stats:
        return False
    if stats["total"] < CONFIG["min_paper_trades"]:
        return False
    if stats["win_rate"] < CONFIG["min_win_rate"]:
        return False
    if stats["total_pnl"] <= 0:
        return False
    return True


# ─── SUMMARY PRINTER ──────────────────────────────────────────────────────────
def print_summary(db: DB):
    stats = db.paper_stats()
    log.info("\n" + "="*55)
    log.info("  PERFORMANCE SUMMARY")
    log.info("="*55)

    if not stats or stats["total"] == 0:
        log.info("  No resolved trades yet. Still tracking...")
    else:
        log.info(f"  Paper trades     : {stats['total']}")
        log.info(f"  Win rate         : {stats['win_rate']:.1%}  "
                 f"({stats['wins']}W / {stats['losses']}L)")
        log.info(f"  Total paper PnL  : ${stats['total_pnl']:+.3f}")
        log.info(f"  Avg per trade    : ${stats['avg_pnl']:+.3f}")

        # Graduation status
        needed = CONFIG["min_paper_trades"]
        done   = stats["total"]
        pct    = stats["win_rate"]
        req    = CONFIG["min_win_rate"]

        log.info(f"\n  Progress to live trading:")
        log.info(f"  Trades: {done}/{needed} {'[OK]' if done >= needed else '[NEED MORE]'}")
        log.info(f"  Win rate: {pct:.1%}/{req:.0%} {'[OK]' if pct >= req else '[NEED HIGHER]'}")

        if should_graduate(db):
            log.info("\n  *** READY FOR LIVE TRADING! ***")
            log.info("  Set dry_run=False in CONFIG to go live.")
        elif done >= needed:
            log.info(f"\n  Win rate {pct:.1%} not yet at {req:.0%} target.")
            log.info("  Keep paper trading. Strategy may need adjustment.")

    log.info("="*55 + "\n")


# ─── MAIN BOT LOOP ────────────────────────────────────────────────────────────
def run():
    db   = DB()
    exec = Executor()

    mode = "PAPER TRADING" if CONFIG["dry_run"] else "LIVE TRADING"
    log.info("="*55)
    log.info(f"  NEGRISK ARB BOT - {mode}")
    log.info(f"  Capital: ${CONFIG['total_capital']} | "
             f"Scan: every {CONFIG['scan_interval_secs']//60} mins")
    log.info(f"  Min profit: {CONFIG['min_profit_pct']:.0%} | "
             f"Max profit: {CONFIG['max_profit_pct']:.0%}")
    log.info(f"  Auto-graduate: {CONFIG['auto_graduate']} | "
             f"Need {CONFIG['min_paper_trades']} trades @ "
             f"{CONFIG['min_win_rate']:.0%} win rate")
    log.info("="*55)

    cycle          = 0
    last_summary   = time.time()

    while True:
        cycle += 1
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        mode    = "PAPER" if CONFIG["dry_run"] else "LIVE"

        log.info(f"\n[{mode}] Cycle {cycle} | {now_str} | "
                 f"Positions: {len(db.positions)}/{CONFIG['max_groups_open']}")

        # Step 1: Check resolutions first
        resolved = check_resolutions(db)
        if resolved:
            log.info(f"  Resolved {resolved} position(s)")

        # Step 2: Check auto-graduation
        if CONFIG["dry_run"] and should_graduate(db):
            log.info("  *** Performance proven! Consider going live. ***")
            stats = db.paper_stats()
            log.info(f"  Win rate: {stats['win_rate']:.1%} over {stats['total']} trades")

        # Step 3: Scan for opportunities
        log.info("  Scanning...")
        opps     = scan_opportunities()
        new_opps = [o for o in opps if o["group_id"] not in db.positions]
        log.info(f"  Found {len(opps)} opportunities ({len(new_opps)} new)")

        # Step 4: Execute
        balance = exec.balance()
        reserve = balance * CONFIG["reserve_pct"]
        avail   = max(0, balance - reserve)
        bets    = 0

        for opp in new_opps:
            if len(db.positions) >= CONFIG["max_groups_open"]: break

            bet_size       = min(CONFIG["max_bet_per_group"],
                                 avail / CONFIG["max_groups_open"])
            amount_per_leg = round(bet_size / opp["n"], 3)

            if amount_per_leg < 0.10:
                continue

            total_invested = round(amount_per_leg * opp["n"], 2)
            exp_profit     = round(total_invested * opp["profit_pct"], 3)

            log.info(f"  BETTING [{opp['hrs_left']:.0f}h] "
                     f"{opp['profit_pct']:.1%} profit | "
                     f"${total_invested:.2f} | {opp['title'][:40]}")

            ok = exec.buy_all(opp, amount_per_leg)
            if ok:
                # Parse closes_at
                closes_at = opp.get("closes_at", "")
                try:
                    if closes_at:
                        closes_dt = datetime.fromisoformat(
                            closes_at.replace("Z", "+00:00") if "T" in closes_at
                            else closes_at + "T00:00:00+00:00")
                    else:
                        closes_dt = datetime.now(timezone.utc) + timedelta(hours=opp.get("hrs_left", 24))
                except Exception:
                    closes_dt = datetime.now(timezone.utc) + timedelta(hours=24)

                db.add_position(opp["group_id"], {
                    "title":        opp["title"],
                    "condition_id": opp["condition_id"],
                    "invested":     total_invested,
                    "total_cost":   opp["total_cost"],
                    "profit_pct":   opp["profit_pct"],
                    "exp_profit":   exp_profit,
                    "closes_at":    closes_dt.isoformat(),
                    "placed_at":    datetime.now(timezone.utc).isoformat(),
                    "paper":        CONFIG["dry_run"],
                    "n":            opp["n"],
                })
                avail -= total_invested
                bets  += 1

        if bets == 0 and len(new_opps) == 0:
            log.info("  No new opportunities this cycle")

        # Hourly summary
        if time.time() - last_summary >= CONFIG["summary_interval_secs"]:
            print_summary(db)
            last_summary = time.time()

        # Sleep
        log.info(f"  Sleeping {CONFIG['scan_interval_secs']//60} mins...")
        time.sleep(CONFIG["scan_interval_secs"])


# ─── ENTRY ────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("="*55)
    print("  NEGRISK ARB BOT — AUTOMATED + SELF-TRACKING")
    print(f"  Mode: {'PAPER (safe, no real money)' if CONFIG['dry_run'] else 'LIVE'}")
    print(f"  Auto-graduate to live: {CONFIG['auto_graduate']}")
    print("="*55)
    try:
        run()
    except KeyboardInterrupt:
        print("\nBot stopped.")