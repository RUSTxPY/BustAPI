import os
from bustapi import BustAPI, jsonify, request, redirect
from bustapi.documentation import BustAPIDocs
from bustapi.jwt import JWT, jwt_required, jwt_optional
import db

# Initialize BustAPI v0.15.0
app = BustAPI(template_folder="templates")
app.secret_key = "super-secret-anime-key" # In prod, use environment variable

# Initialize DB
db.init_db()

# Initialize JWT with Cookie support for browser sessions
jwt = JWT(
    app, 
    token_location=["cookies", "headers"],
    access_cookie_name="anime_access_token",
    cookie_httponly=True,
    cookie_secure=False, # Set to True in production with HTTPS
)

# Setup Storage
STORAGE_DIR = os.path.expanduser("~/storage")
os.makedirs(STORAGE_DIR, exist_ok=True)
app._rust_app.add_static_route("/storage", STORAGE_DIR)

# Enable Swagger Documentation
docs = BustAPIDocs(
    app, 
    title="AnimeBust API", 
    version="0.15.0", 
    description="The world's fastest anime streaming backend with JWT Auth."
)

# Mock Data for Templates
ANIME_DATA = [
    {"title": "Solo Leveling", "rating": "9.8", "genre": "Action", "episodes": 12, "image": "https://m.media-amazon.com/images/M/MV5BODcwNWE3OTItMDdmZC00ZWJmLWE0NTEtMDkyMmE0MWU2NjZhXkEyXkFqcGdeQXVyMTA0MTM5NjI2._V1_.jpg", "desc": "In a world where hunters must battle deadly monsters..."},
    {"title": "Jujutsu Kaisen S2", "rating": "9.5", "genre": "Supernatural", "episodes": 23, "image": "https://m.media-amazon.com/images/M/MV5BMTMwMDM4N2EtOTJiYy00OTQ0LThlZDYtYWUwOWRjNjlhYzFmXkEyXkFqcGdeQXVyMTMzNDExODE5._V1_.jpg", "desc": "The Shibuya Incident begins."},
    {"title": "Demon Slayer", "rating": "9.2", "genre": "Fantasy", "episodes": 52, "image": "https://m.media-amazon.com/images/M/MV5BZjZjNzI5MDctY2Y4YS00NmM4LTg0ZDMtOTkwZTI1MTExNWZlXkEyXkFqcGdeQXVyMTMxODk2OTU@._V1_.jpg", "desc": "Tanjiro Kamado sets out to find a cure for his sister."},
    {"title": "Frieren", "rating": "9.4", "genre": "Adventure", "episodes": 28, "image": "https://m.media-amazon.com/images/M/MV5BYmUyZWYyOTgtOWExMi00NDBjLTk4Y2ItZTA0YTM1ZTE1YjA3XkEyXkFqcGdeQXVyMTEzMTI1Mjk3._V1_.jpg", "desc": "Elf mage Frieren and her fellow adventurers have defeated the Demon King."}
]

# --- 🛠️ AUTH HANDLERS ---

@app.route("/api/register", methods=["POST"])
def api_register():
    data = request.get_json()
    username = data.get("username")
    email = data.get("email")
    password = data.get("password")
    
    if not all([username, email, password]):
        return jsonify({"error": "Missing fields"}), 400
        
    if db.create_user(username, email, password):
        return jsonify({"message": "User created successfully"}), 201
    return jsonify({"error": "User already exists"}), 409

@app.route("/api/login", methods=["POST"])
def api_login():
    data = request.get_json()
    email = data.get("email")
    password = data.get("password")
    
    user = db.authenticate_user(email, password)
    if user:
        access_token = jwt.create_access_token(identity=user["id"])
        resp = jsonify({"message": "Login successful", "user": user})
        jwt.set_access_cookies(resp, access_token)
        return resp
    
    return jsonify({"error": "Invalid credentials"}), 401

@app.route("/logout")
def logout():
    resp = redirect("/login")
    jwt.unset_jwt_cookies(resp)
    return resp

# --- 🌐 PAGE HANDLERS (Dynamic with JWT) ---

@app.route("/")
@jwt_optional
def index():
    user = None
    if request.jwt_identity:
        user = db.get_user_by_id(request.jwt_identity)
    return app.render_template("index.html", animes=ANIME_DATA, user=user)

@app.route("/dashboard")
@jwt_required
def dashboard():
    user = db.get_user_by_id(request.jwt_identity)
    return app.render_template("dashboard.html", user=user)

@app.route("/login")
@jwt_optional
def login_page():
    if request.jwt_identity:
        return redirect("/dashboard")
    return app.render_template("login.html")

@app.route("/register")
def register_page():
    return app.render_template("login.html") # Same template, JS toggles

@app.route("/profile")
@jwt_required
def profile_page():
    user = db.get_user_by_id(request.jwt_identity)
    return app.render_template("profile.html", user=user)

@app.route("/api/profile/avatar", methods=["POST"])
@jwt_required
def api_avatar_upload():
    if not request.files:
        return jsonify({"error": "No files uploaded"}), 400
        
    file = request.files.get("avatar")
    if not file:
        return jsonify({"error": "Avatar file missing"}), 400
        
    # Save file
    filename = f"user_{request.jwt_identity}_{file.filename}"
    save_path = os.path.join(STORAGE_DIR, filename)
    
    with open(save_path, "wb") as f:
        f.write(file.data)
        
    avatar_url = f"/storage/{filename}"
    db.update_avatar(request.jwt_identity, avatar_url)
    
    return jsonify({"message": "Avatar updated", "url": avatar_url})

@app.route("/api/profile/update", methods=["POST"])
@jwt_required
def api_profile_update():
    data = request.get_json()
    db.update_user(
        request.jwt_identity, 
        username=data.get("username"), 
        email=data.get("email"),
        password=data.get("password")
    )
    return jsonify({"message": "Profile updated"})

# --- 🚀 FAST ROUTES (Static Data) ---

@app.fast_route("/api/status")
def api_status():
    return {"status": "operational", "engine": "BustAPI v0.15.0", "jwt": "enabled"}

@app.fast_route("/api/version")
def api_version():
    return {"version": "0.15.0", "db": "SQLite"}

if __name__ == "__main__":
    # Use multiple workers for production feel
    app.run(host="0.0.0.0", port=8080, workers=4, debug=False)
