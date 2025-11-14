import secrets

print("=" * 60)
print("AZURE APP SERVICE ENVIRONMENT VARIABLES")
print("=" * 60)
print(f"\nSESSION_SECRET={secrets.token_hex(32)}")
print("\nCopy the above value to Azure App Service Configuration")
print("=" * 60)