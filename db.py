print("🧪 Starting DB connection test...")

from dotenv import load_dotenv
import os
import pyodbc

# Load .env
load_dotenv()
print("📌 .env loaded")

# Read variables
server = os.getenv("AZURE_SQL_SERVER")
db = os.getenv("AZURE_SQL_DATABASE")
user = os.getenv("AZURE_SQL_USERNAME")
pwd = os.getenv("AZURE_SQL_PASSWORD")

print("🔍 Checking env vars:")
print("SERVER:", server)
print("DATABASE:", db)
print("USERNAME:", user)
print("PASSWORD:", "********")  # Do not print password

if not server or not db or not user or not pwd:
    print("❌ Missing environment variables!")
    exit()

print("⚙️ Building connection string...")

connection_string = (
    f"DRIVER={{ODBC Driver 18 for SQL Server}};"
    f"SERVER={server},1433;"
    f"DATABASE={db};"
    f"UID={user};"
    f"PWD={pwd};"
    f"Encrypt=yes;"
    f"TrustServerCertificate=yes;"
    f"Connection Timeout=90;"
)

print("🔌 Connecting to SQL... (up to 90s)")
try:
    conn = pyodbc.connect(connection_string)
    print("🎉 CONNECTED TO SQL!")
    cursor = conn.cursor()
    cursor.execute("SELECT GETDATE();")
    print("⏱ Server time:", cursor.fetchone())
    conn.close()

except Exception as e:
    print("🔥 ERROR:", e)
