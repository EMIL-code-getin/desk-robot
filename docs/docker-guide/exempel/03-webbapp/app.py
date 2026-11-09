import os
import socket

from flask import Flask

app = Flask(__name__)

# Texten kan bytas utan att bygga om imagen: docker run -e HALSNING="..."
HALSNING = os.environ.get("HALSNING", "Hej från Flask i en container!")


@app.route("/")
def start():
    return f"<h1>{HALSNING}</h1><p>Containerns namn: {socket.gethostname()}</p>"


if __name__ == "__main__":
    # 0.0.0.0 betyder "lyssna på alla nätverkskort". Med standardvärdet
    # 127.0.0.1 hade appen bara gått att nå inifrån containern själv.
    app.run(host="0.0.0.0", port=5000)
