import os

import redis
from flask import Flask

app = Flask(__name__)

# "databas" är namnet på tjänsten i compose.yaml. Docker gör så att
# containrar i samma compose-projekt hittar varandra på tjänstens namn.
databas = redis.Redis(host=os.environ.get("REDIS_HOST", "databas"), port=6379)


@app.route("/")
def start():
    antal = databas.incr("besok")
    return f"<h1>Den här sidan har visats {antal} gånger.</h1>"


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
