# En färdig image med Python installerat. "slim" är en mindre variant.
FROM python:3.13-slim

# Mappen inuti containern som resten av raderna utgår från.
WORKDIR /app

# Kopiera in programmet från din dator till /app i imagen.
COPY hej.py .

# Det som körs när containern startar.
CMD ["python", "hej.py"]
