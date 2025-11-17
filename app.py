from flask import Flask, request, jsonify, render_template_string
from epicwin import make_device_profile, build_headers, login, get_balance

app = Flask(__name__)

# Pre-generate device profile + headers
device_profile = make_device_profile("web-user")
HEADERS = build_headers(device_profile)

# ---------- HTML TEMPLATES ----------

LOGIN_FORM_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>EpicWin Login</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            background: #0f172a;
            color: #e5e7eb;
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
            margin: 0;
        }
        .card {
            background: #020617;
            border: 1px solid #1e293b;
            border-radius: 12px;
            padding: 24px;
            width: 320px;
            box-shadow: 0 10px 25px rgba(15,23,42,0.8);
        }
        h1 {
            font-size: 1.25rem;
            margin-bottom: 0.25rem;
        }
        p.subtitle {
            font-size: 0.8rem;
            margin-top: 0;
            margin-bottom: 1.2rem;
            color: #9ca3af;
        }
        label {
            display: block;
            font-size: 0.8rem;
            margin-bottom: 4px;
        }
        input[type="text"],
        input[type="password"] {
            width: 100%;
            padding: 8px 10px;
            border-radius: 8px;
            border: 1px solid #374151;
            background: #020617;
            color: #e5e7eb;
            box-sizing: border-box;
            margin-bottom: 12px;
        }
        input[type="text"]:focus,
        input[type="password"]:focus {
            outline: none;
            border-color: #3b82f6;
        }
        button {
            width: 100%;
            padding: 9px 12px;
            border-radius: 8px;
            border: none;
            background: #3b82f6;
            color: white;
            font-weight: 600;
            cursor: pointer;
        }
        button:hover {
            background: #2563eb;
        }
        .error {
            color: #fecaca;
            background: #450a0a;
            border-radius: 8px;
            padding: 8px 10px;
            font-size: 0.8rem;
            margin-bottom: 10px;
        }
    </style>
</head>
<body>
    <div class="card">
        <h1>EpicWin Login</h1>
        <p class="subtitle">Enter your account credentials to generate a session token.</p>

        {% if error %}
            <div class="error">{{ error }}</div>
        {% endif %}

        <form method="post" action="/login">
            <label for="account_id">Account ID</label>
            <input type="text" id="account_id" name="account_id" required>

            <label for="password">Password / PIN</label>
            <input type="password" id="password" name="password" required>

            <button type="submit">Login</button>
        </form>
    </div>
</body>
</html>
"""

LOGIN_RESULT_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>EpicWin Login Result</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            background: #0f172a;
            color: #e5e7eb;
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
            margin: 0;
        }
        .card {
            background: #020617;
            border: 1px solid #1e293b;
            border-radius: 12px;
            padding: 24px;
            width: 360px;
            box-shadow: 0 10px 25px rgba(15,23,42,0.8);
        }
        h1 {
            font-size: 1.25rem;
            margin-bottom: 0.25rem;
        }
        p.subtitle {
            font-size: 0.8rem;
            margin-top: 0;
            margin-bottom: 1.2rem;
            color: #9ca3af;
        }
        .field {
            margin-bottom: 8px;
            font-size: 0.9rem;
        }
        .label {
            color: #9ca3af;
        }
        .value {
            font-weight: 600;
        }
        .token-box {
            background: #020617;
            border-radius: 8px;
            border: 1px dashed #4b5563;
            padding: 8px 10px;
            word-break: break-all;
            font-size: 0.76rem;
            margin-top: 4px;
        }
        a.button {
            display: inline-block;
            margin-top: 14px;
            padding: 8px 12px;
            border-radius: 8px;
            background: #3b82f6;
            color: white;
            font-size: 0.85rem;
            text-decoration: none;
        }
        a.button:hover {
            background: #2563eb;
        }
        .error {
            color: #fecaca;
            background: #450a0a;
            border-radius: 8px;
            padding: 8px 10px;
            font-size: 0.8rem;
            margin-bottom: 10px;
        }
    </style>
</head>
<body>
    <div class="card">
        <h1>Login Result</h1>
        <p class="subtitle">Below is the response returned by the EpicWin login API.</p>

        {% if error %}
            <div class="error">{{ error }}</div>
        {% else %}
            <div class="field">
                <span class="label">HTTP Status:&nbsp;</span>
                <span class="value">{{ status_code }}</span>
            </div>
            <div class="field">
                <span class="label">Account ID:&nbsp;</span>
                <span class="value">{{ account_id }}</span>
            </div>
            <div class="field">
                <span class="label">Token:</span>
                <div class="token-box">{{ token or '(no token returned)' }}</div>
            </div>
        {% endif %}

        <a href="/login" class="button">Back to Login</a>
    </div>
</body>
</html>
"""

# ---------- ROUTES ----------

@app.route("/")
def index():
    return "EpicWin Web Server Active"

@app.route("/login", methods=["GET", "POST"])
def web_login():
    # GET -> show HTML form
    if request.method == "GET":
        return render_template_string(LOGIN_FORM_HTML)

    # POST -> JSON API (for Postman, etc.)
    if request.is_json:
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

    # POST -> from HTML form
    account_id = request.form.get("account_id", "").strip()
    password = request.form.get("password", "").strip()

    if not account_id or not password:
        return render_template_string(
            LOGIN_FORM_HTML,
            error="Both account ID and password are required."
        )

    token, acct_from_login, (code, resp) = login(account_id, password, headers=HEADERS)

    # If the API failed or returned error-like status
    if not code or code >= 400:
        return render_template_string(
            LOGIN_RESULT_HTML,
            error=f"Login failed (status {code}). Raw response: {resp}",
            status_code=code or "N/A",
            account_id=acct_from_login or account_id,
            token=token,
        )

    # Success
    return render_template_string(
        LOGIN_RESULT_HTML,
        error=None,
        status_code=code,
        account_id=acct_from_login or account_id,
        token=token,
    )

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
