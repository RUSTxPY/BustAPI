import os
from bustapi import BustAPI, request, jsonify
from bustapi.jwt import JWT, jwt_required

app = BustAPI()
app.secret_key = "turbomax_super_secret_key_for_testing"

jwt = JWT(
    app,
    token_location=["cookies", "headers"],
    access_cookie_name="access_token"
)

# Mock DB
MOCK_DB = {
    "user_123": {
        "id": "user_123",
        "name": "Grandpa",
        "role": "admin"
    }
}

@app.route("/login", methods=["POST"])
def login():
    # Simple login to set JWT cookie and session
    request.session["visits"] = 1
    token = jwt.create_access_token(identity="user_123")
    resp = jsonify({"msg": "Logged in"})
    jwt.set_access_cookies(resp, token)
    return resp

@app.route("/api/business_logic", methods=["GET"])
@jwt_required
def business_logic():
    # 1. Access Session
    visits = request.session.get("visits", 0)
    request.session["visits"] = visits + 1
    
    # 2. Access JWT Identity
    user_id = request.jwt_identity
    
    # 3. Mock DB lookup
    user = MOCK_DB.get(user_id, {"id": "unknown", "name": "Guest"})
    
    # 4. Access Query Params
    sort_by = request.args.get("sort_by", "date")
    
    # 5. Return JSON via jsonify (creates Response object)
    return jsonify({
        "status": "success",
        "user": user,
        "visits": visits,
        "sort_by": sort_by
    })

@app.route("/api/business_logic_raw", methods=["GET"])
@jwt_required
def business_logic_raw():
    """Same as above but returns raw dict — Rust serializes directly"""
    visits = request.session.get("visits", 0)
    request.session["visits"] = visits + 1
    
    user_id = request.jwt_identity
    user = MOCK_DB.get(user_id, {"id": "unknown", "name": "Guest"})
    sort_by = request.args.get("sort_by", "date")
    
    return {
        "status": "success",
        "user": user,
        "visits": visits,
        "sort_by": sort_by
    }

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, workers=1, debug=False)
