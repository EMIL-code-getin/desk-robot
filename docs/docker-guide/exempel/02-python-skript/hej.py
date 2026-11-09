import os
import platform

# Läser miljövariabeln NAMN. Finns den inte används "världen".
namn = os.environ.get("NAMN", "världen")

print(f"Hej {namn}!")
print(f"Jag körs med Python {platform.python_version()} inuti en container.")
