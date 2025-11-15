 #!/bin/bash
set -e

echo "📌 Updating apt..."
apt-get update -y

echo "📌 Installing system dependencies for pyodbc..."
apt-get install -y curl apt-transport-https gnupg unixodbc-dev

echo "📌 Adding Microsoft SQL Server ODBC repo..."
curl https://packages.microsoft.com/keys/microsoft.asc | apt-key add -
curl https://packages.microsoft.com/config/debian/11/prod.list \
    > /etc/apt/sources.list.d/msprod.list

apt-get update -y

echo "📌 Installing Microsoft SQL Server ODBC driver..."
ACCEPT_EULA=Y apt-get install -y msodbcsql17

echo "📦 Installing Python packages..."
pip install Flask==3.0.0
pip install Werkzeug==3.0.1
pip install pyodbc==5.0.1
pip install google-generativeai==0.3.2
pip install Pillow==10.1.0
pip install -U "requests>=2.31.0"

echo "🚀 Starting Gunicorn server..."
gunicorn app:app --bind=0.0.0.0:8000 --timeout 120 --access-logfile - --error-logfile -
