from flask import Flask, request, jsonify
from try import make_device_profile, build_headers, login, get_balance

app = Flask(__name__)

# Pre-generate device profile + headers
device_profile = make_device_profile("web-user")
HEADERS = build_headers(device_profile)

@app.route("/")
def index():
    return "EpicWin Web Server Active"

@app.route("/login", methods=["POST"])
def web_login():
    data = request.get_json(force=True)
    account_id = data.get("account_id", "").strip()
    password = data.get("password", "").strip()

    if not account_id or not password:
        return jsonify({"error": "Both account_id and password are required"}), 400

    token, acct_from_login, (code, resp) = login(account_id, password, headers=HEADERS)

    return jsonify({
        "status_code": code,
        "account_id": acct_from_login or account_id,
        "token": token,
        "response": resp,
    }), code or 500

@app.route("/balance", methods=["POST"])
def check_balance():
    data = request.get_json(force=True)
    account_id = data.get("account_id", "").strip()
    token = data.get("token", "").strip()

    if not account_id or not token:
        return jsonify({"error": "account_id and token required"}), 400

    code, resp = get_balance(account_id, token, headers=HEADERS)

    return jsonify({
        "status_code": code,
        "response": resp
    }), code or 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
