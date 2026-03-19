from py_clob_client.client import ClobClient

# Put your MetaMask private key here first
PRIVATE_KEY = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"

client = ClobClient(
    host="https://clob.polymarket.com",
    key=PRIVATE_KEY,
    chain_id=137,
)

# This generates your API key, secret, passphrase
creds = client.create_api_key()

print("POLY_API_KEY=",     creds.api_key)
print("POLY_API_SECRET=",  creds.api_secret)
print("POLY_PASSPHRASE=",  creds.api_passphrase)
print("POLY_PRIVATE_KEY=", PRIVATE_KEY)