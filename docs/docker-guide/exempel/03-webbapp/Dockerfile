FROM python:3.13-slim

# Gör att utskrifter syns direkt i "docker logs".
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Steg 1: kopiera bara listan över paket och installera dem.
# Den här delen sparas (cachas) och görs bara om när listan ändras.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Steg 2: kopiera koden. Den ändras ofta, så den ligger sist.
COPY app.py .

# Dokumenterar vilken port appen lyssnar på inuti containern.
EXPOSE 5000

CMD ["python", "app.py"]
