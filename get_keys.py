"""
GET POLYMARKET API KEYS — FIXED VERSION
Run: python get_keys.py
"""
from py_clob_client.client import ClobClient

# ── FILL THESE IN ──────────────────────────────────────────
PRIVATE_KEY  = "0x_your_metamask_private_key_here"
PROXY_WALLET = "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266"  # from Polymarket screen
# ───────────────────────────────────────────────────────────

print("Connecting to Polymarket CLOB...")

try:
    # Method 1: signature_type=2 (for wallets connected via Polymarket website)
    client = ClobClient(
        host="https://clob.polymarket.com",
        key=PRIVATE_KEY,
        chain_id=137,
        signature_type=2,
        funder=PROXY_WALLET,
    )
    creds = client.create_api_key()
    print("\n✅ SUCCESS! Copy these into your .env file:\n")
    print(f"POLY_API_KEY={creds.api_key}")
    print(f"POLY_API_SECRET={creds.api_secret}")
    print(f"POLY_PASSPHRASE={creds.api_passphrase}")
    print(f"POLY_PRIVATE_KEY={PRIVATE_KEY}")
    print(f"POLY_PROXY_WALLET={PROXY_WALLET}")

except Exception as e1:
    print(f"Method 1 failed: {e1}")
    print("Trying Method 2 (direct EOA wallet)...")

    try:
        # Method 2: direct wallet, no proxy
        client2 = ClobClient(
            host="https://clob.polymarket.com",
            key=PRIVATE_KEY,
            chain_id=137,
        )
        creds = client2.create_api_key()
        print("\n✅ SUCCESS! Copy these into your .env file:\n")
        print(f"POLY_API_KEY={creds.api_key}")
        print(f"POLY_API_SECRET={creds.api_secret}")
        print(f"POLY_PASSPHRASE={creds.api_passphrase}")
        print(f"POLY_PRIVATE_KEY={PRIVATE_KEY}")
        print(f"POLY_PROXY_WALLET={PROXY_WALLET}")

    except Exception as e2:
        print(f"Method 2 failed: {e2}")
        print("\n❌ Both methods failed.")
        print("\nMost likely cause: wallet not registered on Polymarket yet.")
        print("\nFix:")
        print("  1. Go to polymarket.com")
        print("  2. Make sure MetaMask is connected")
        print("  3. Accept terms of service if prompted")
        print("  4. Make a small manual trade or deposit first")
        print("  5. Then run this script again")
