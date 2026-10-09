from livereload import Server
from app import app

# Show updated HTML templates without restarting the app.
app.config["TEMPLATES_AUTO_RELOAD"] = True

server = Server(app.wsgi_app)

# Refresh the browser when these files change.
server.watch("app.py")
server.watch("templates/")
server.watch("static/")

server.serve(host="127.0.0.1", port=5001)