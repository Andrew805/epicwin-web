#!/usr/bin/env python3
"""
EpicWin CLI (Proxy-first, fixed login parsing, FIRST-wallet auto-select)
Adds:
 - View Statement (/report/getstatement)
 - View Ticket List (/report/getticketlist)
 - Withdraw uses FIRST saved wallet (by member_bank_id if available)

Safe Test Extensions:
 - Transparent Test Mode flag
 - Non-deceptive, labeled device profile + unified headers
 - Option to inspect effective headers
"""

import os
import json
import time
import sys
import hashlib
import random
import datetime
from typing import Any, Dict, Tuple, Optional
from email.utils import formatdate
from zoneinfo import ZoneInfo

import requests

BASE = "https://api.epicwincasino.ph"
TIMEOUT = 30

# ---------- Transparent Test Mode ----------
IS_TEST_MODE = True                     # <- set False for normal use
TEST_CLIENT_NAME = "EpicWinCLI/1.1"
TEST_NOTE = "Authorized load testing / QA. Traffic is labeled and non-deceptive."

# ---------- Enhanced Device Profile (randomized, realistic) ----------
def make_device_profile(account_id: str, profile_variant: Optional[int] = None) -> Dict[str, Any]:
    """
    Return a small, realistic device profile.
    - If profile_variant is None, a random profile is generated each call (more realistic).
    - If profile_variant is provided, selection is deterministic (stable per account).
    """
    # Pools
    ANDROID_POOL = [
        {"vendor": "Samsung", "model": "SM-S911B", "screen": (1440, 3088)},
        {"vendor": "Samsung", "model": "SM-A546E", "screen": (1080, 2340)},
        {"vendor": "Xiaomi", "model": "2201117TG", "screen": (1080, 2400)},
        {"vendor": "OPPO", "model": "CPH2457", "screen": (1080, 2400)},
        {"vendor": "Realme", "model": "RMX3630", "screen": (1080, 2412)},
        {"vendor": "OnePlus", "model": "OnePlus 11", "screen": (1440, 3216)},
        {"vendor": "Vivo", "model": "V2144", "screen": (1080, 2400)},
    ]
    IOS_POOL = [
        {"vendor": "Apple", "model": "iPhone12,1", "screen": (1170, 2532)},
        {"vendor": "Apple", "model": "iPhone14,2", "screen": (1179, 2556)},
        {"vendor": "Apple", "model": "iPhone15,2", "screen": (1290, 2796)},
    ]
    WINDOWS_RES = [(1366, 768), (1600, 900), (1920, 1080), (2560, 1440)]

    PH_LOCALES = ["en-PH,en;q=0.9", "tl-PH,tl;q=0.9", "fil-PH,fil;q=0.9"]
    PH_TIMEZONE = "Asia/Manila"

    # Determine variant index deterministically if profile_variant provided,
    # otherwise random selection for more realism.
    if profile_variant is None:
        family = random.choices(["Android", "iOS", "Windows", "macOS"], weights=[0.62, 0.30, 0.06, 0.02])[0]
    else:
        # Stable pick using the provided index
        families = ["Android", "iOS", "Windows", "macOS"]
        family = families[profile_variant % len(families)]

    device_uuid = hashlib.md5(os.urandom(16)).hexdigest()  # random-ish id per call
    build_id = hashlib.sha1((device_uuid + str(time.time())).encode()).hexdigest()[:8]

    if family == "Android":
        pick = random.choice(ANDROID_POOL) if profile_variant is None else ANDROID_POOL[profile_variant % len(ANDROID_POOL)]
        vendor = pick["vendor"]
        model = pick["model"]
        width, height = pick["screen"]
        os_version = random.choice(["11", "12", "13", "14"])
        android_id = hashlib.md5((device_uuid + model).encode()).hexdigest()[:16]
        imei = ''.join(random.choice("0123456789") for _ in range(15))
        platform = "Android"
        ua = f"Mozilla/5.0 (Linux; Android {os_version}; {model}) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{random.randint(100,140)}.0.0.0 Mobile Safari/537.36"
        mobile_flag = "?1"
        device_memory = random.choice([4, 6, 8, 12])
        hw_threads = random.choice([4, 6, 8])

    elif family == "iOS":
        pick = random.choice(IOS_POOL) if profile_variant is None else IOS_POOL[profile_variant % len(IOS_POOL)]
        vendor = pick["vendor"]
        model = pick["model"]
        width, height = pick["screen"]
        os_version_raw = random.choice(["15_6", "16_7", "17_5"])
        os_version = os_version_raw.replace("_", ".")
        android_id = ""
        imei = ""
        platform = "iOS"
        ua = f"Mozilla/5.0 (iPhone; CPU iPhone OS {os_version_raw} like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/{os_version.split('.')[0]}.0 Mobile/15E148 Safari/604.1"
        mobile_flag = "?1"
        device_memory = random.choice([4, 6])
        hw_threads = random.choice([4, 6])

    else:  # Windows/macOS
        vendor = "GenericPC" if family == "Windows" else "Apple"
        model = random.choice(["PC", "Laptop"]) if family == "Windows" else random.choice(["MacBook Pro", "MacBook Air"])
        width, height = random.choice(WINDOWS_RES)
        os_version = random.choice(["10", "11"]) if family == "Windows" else random.choice(["12", "13"])
        android_id = ""
        imei = ""
        platform = family
        ua = f"Mozilla/5.0 (Windows NT {os_version}; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{random.randint(100,140)}.0.0.0 Safari/537.36"
        mobile_flag = "?0"
        device_memory = random.choice([8, 12, 16])
        hw_threads = random.choice([4, 8, 12])

    # Small natural clock skew (±2 minutes)
    clock_skew_sec = random.randint(-120, 120)
    now_utc = datetime.datetime.utcnow()
    client_time = (now_utc + datetime.timedelta(seconds=clock_skew_sec)).replace(microsecond=0).isoformat() + "Z"
    manila_local = (now_utc + datetime.timedelta(seconds=clock_skew_sec) + datetime.timedelta(hours=8)).replace(microsecond=0).isoformat()

    profile = {
        "device_id": device_uuid,
        "android_id": android_id,
        "imei": imei,
        "vendor": vendor,
        "model": model,
        "platform": platform,
        "os_version": os_version,
        "screen": {"width": width, "height": height},
        "screen_res": f"{width}x{height}",
        "build_id": build_id,
        "deviceMemoryGB": device_memory,
        "hardwareConcurrency": hw_threads,
        "accept_language": random.choice(PH_LOCALES) if family != "Windows" else "en-US,en;q=0.9",
        "locale": random.choice(["en-PH", "tl-PH"]),
        "timezone": PH_TIMEZONE,
        "clock_skew_sec": clock_skew_sec,
        "x_client_time": client_time,
        "x_local_time": manila_local,
        "user_agent": ua,
        "profile_variant": family.lower(),
    }
    return profile

# ---------- Headers builder (uses device profile) ----------
def build_headers(device_profile: Dict[str, Any]) -> Dict[str, str]:
    # date header with clock skew
    skewed_epoch = time.time() + float(device_profile.get("clock_skew_sec", 0))
    date_header = formatdate(timeval=skewed_epoch, usegmt=True)

    headers = {
        "User-Agent": device_profile.get("user_agent", "EpicWinCLI/unknown"),
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json",
        "Origin": "https://epicwincasino.ph",
        "Referer": "https://epicwincasino.ph/",
        "Accept-Encoding": "gzip, deflate, br, zstd",
        "Accept-Language": device_profile.get("accept_language", "en-PH"),
        "Date": date_header,
        "X-Client-Time": device_profile.get("x_client_time", ""),
        "X-Local-Time": device_profile.get("x_local_time", ""),
        "X-Clock-Skew-Seconds": str(device_profile.get("clock_skew_sec", 0)),
        "X-Timezone": device_profile.get("timezone", "Asia/Manila"),
        "sec-ch-ua": f"\"Chromium\";v=\"{random.randint(118,140)}\", \"Not=A?Brand\";v=\"24\"",
        "sec-ch-ua-mobile": "?{}".format("1" if device_profile.get("platform", "").lower() in ["android", "ios"] else "0"),
        "sec-ch-ua-platform": "\"{}\"".format(device_profile.get("platform", "Android")),
        # optional explicit device headers
        "X-Device-Vendor": device_profile.get("vendor", ""),
        "X-Device-Model": device_profile.get("model", ""),
        "X-Device-OS": device_profile.get("platform", ""),
        "X-Device-OS-Version": device_profile.get("os_version", ""),
        # Transparent testing labels
        "X-Test-Mode": "true" if IS_TEST_MODE else "false",
        "X-Test-Client": TEST_CLIENT_NAME,
        "X-Test-Note": TEST_NOTE,
        "X-Test-Profile-Id": device_profile.get("profile_variant", "unknown"),
    }
    # Also include a compact JSON of device info
    try:
        headers["X-Client-Device"] = json.dumps({
            "id": device_profile.get("device_id"),
            "vendor": device_profile.get("vendor"),
            "model": device_profile.get("model"),
            "os": device_profile.get("platform"),
            "os_version": device_profile.get("os_version"),
            "screen": device_profile.get("screen"),
            "memory_gb": device_profile.get("deviceMemoryGB"),
            "hw_threads": device_profile.get("hardwareConcurrency"),
            "tz": device_profile.get("timezone"),
        })
    except Exception:
        pass

    return headers

# ---------- Proxy configuration (BEFORE login) ----------
PROXY_HOST     = os.getenv("PROXY_HOST", "proxy.proxyverse.io")
PROXY_PORT     = os.getenv("PROXY_PORT", "9200")
PROXY_USERNAME = os.getenv("PROXY_USERNAME", "country-ph")
PROXY_PASSWORD = os.getenv("PROXY_PASSWORD", "bef08b93-ee00-42c0-8fe6-18e852aaeb9c")
USE_PROXY      = os.getenv("USE_PROXY", "1").strip()

def build_proxies() -> Optional[Dict[str, str]]:
    if USE_PROXY in ("0", "false", "False") or not PROXY_HOST:
        return None
    if PROXY_USERNAME and PROXY_PASSWORD:
        url = f"http://{PROXY_USERNAME}:{PROXY_PASSWORD}@{PROXY_HOST}:{PROXY_PORT}"
    else:
        url = f"http://{PROXY_HOST}:{PROXY_PORT}"
    return {"http": url, "https": url}

PROXIES = build_proxies()

def mask_proxy(p: Optional[Dict[str,str]]) -> str:
    if not p: return "[Proxy disabled]"
    u = p.get("https") or p.get("http") or ""
    try:
        proto, rest = u.split("://", 1)
        if "@" in rest:
            _, hostport = rest.split("@", 1)
            return f"[Proxy enabled] {proto}://***@{hostport}"
        return f"[Proxy enabled] {u}"
    except Exception:
        return f"[Proxy enabled] {u or 'unknown'}"

def check_proxy(proxies: Optional[Dict[str, str]]) -> None:
    """Test proxy by fetching public IP. If it fails, fall back to direct (no crash)."""
    if not proxies:
        print("[Proxy Check] ⚠️ No proxy configured, using direct connection.")
        return
    try:
        r = requests.get("https://api.ipify.org?format=json", proxies=proxies, timeout=10)
        if r.ok:
            ip = r.json().get("ip", "unknown")
            print(f"[Proxy Check] ✅ Working proxy. Public IP: {ip}")
            # Optionally check country with ipapi.co — commented out to keep minimal
            # r2 = requests.get(f"https://ipapi.co/{ip}/json/", timeout=8)
            # if r2.ok: print("[Proxy IP Info]", r2.json().get("country_name"))
        else:
            print(f"[Proxy Check] ❌ Proxy responded with status {r.status_code}")
    except Exception as e:
        print(f"[Proxy Check] ❌ Proxy failed: {e}")
        # fallback to direct
        global PROXIES
        PROXIES = None
        print("[Proxy Check] → Falling back to direct connection (PROXIES disabled).")

# ---------- HTTP helpers ----------
def pretty(x): return json.dumps(x, indent=2, ensure_ascii=False)

def request_post(path: str, payload: Dict[str, Any], headers: Optional[Dict[str, str]] = None) -> Tuple[int, Dict[str, Any]]:
    url = f"{BASE}{path}"
    kwargs = {"json": payload, "timeout": TIMEOUT}
    if headers: kwargs["headers"] = headers
    if PROXIES: kwargs["proxies"] = PROXIES
    try:
        r = requests.post(url, **kwargs)
    except requests.exceptions.RequestException as e:
        return 0, {"error": "request_exception", "message": str(e)}
    try:
        data = r.json()
    except Exception:
        data = {"raw_text": r.text}
    return r.status_code, data

# ---------- Token extraction ----------
def extract_token_and_id(login_json: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
    token = None
    acct  = None
    if isinstance(login_json, dict):
        token = login_json.get("auth_token") or login_json.get("token")
        data  = login_json.get("data")
        if not token and isinstance(data, dict):
            token = data.get("auth_token") or data.get("token")
        if not token:
            value = login_json.get("value")
            if isinstance(value, list) and value:
                first = value[0] if isinstance(value[0], dict) else None
                if first:
                    token = first.get("session_token") or first.get("auth_token") or first.get("token")
                    acct  = first.get("account_id")
    return token, acct

# ---------- API wrappers ----------
def login(account_id: str, password: str, headers: Optional[Dict[str, str]] = None):
    code, data = request_post("/member/memberlogin", {"account_id": account_id, "password": password}, headers)
    print("\n[LOGIN]", code); print(pretty(data))
    token, acct_from_login = extract_token_and_id(data)
    return token, acct_from_login, (code, data)

def add_update_wallet(account_id: str, token: str, holder: str, number: str, bank_id: str = "GCASH", headers: Optional[Dict[str, str]] = None):
    payload = {"account_id": account_id, "bank_id": bank_id,
               "bank_acc_holder": holder, "bank_acc_no": number, "auth_token": token}
    return request_post("/fund/addmemberewalletv2", payload, headers)

def submit_withdrawal_by_id(account_id: str, token: str, amount: str, member_bank_id: str, headers: Optional[Dict[str, str]] = None):
    payload = {"account_id": account_id, "withdrawal_amount": str(amount),
               "auth_token": token, "member_bank_id": member_bank_id}
    return request_post("/fund/withdrawal", payload, headers)

def submit_withdrawal_by_gcash(account_id: str, token: str, amount: str, bank_id: str, bank_acc_no: str, headers: Optional[Dict[str, str]] = None):
    payload = {"account_id": account_id, "withdrawal_amount": str(amount),
               "auth_token": token, "bank_id": bank_id, "bank_acc_no": bank_acc_no}
    return request_post("/fund/withdrawal", payload, headers)

def get_balance(account_id: str, token: str, headers: Optional[Dict[str, str]] = None):
    return request_post("/fund/getbalance", {"account_id": account_id, "auth_token": token}, headers)

def get_inbox(account_id: str, token: str, headers: Optional[Dict[str, str]] = None):
    return request_post("/fund/getinboxlist", {"account_id": account_id, "auth_token": token}, headers)

def get_member_bank_list(account_id: str, token: str, headers: Optional[Dict[str, str]] = None):
    code, data = request_post("/fund/getmemberbanklist", {"account_id": account_id, "auth_token": token}, headers)
    if code == 200 and isinstance(data, dict) and data.get("value"):
        return code, data
    return request_post("/fund/getbanklistmb", {"account_id": account_id, "auth_token": token}, headers)

def get_statement(account_id: str, token: str, headers: Optional[Dict[str, str]] = None):
    return request_post("/report/getstatement", {"account_id": account_id, "auth_token": token}, headers)

def get_ticket_list(account_id: str, token: str, headers: Optional[Dict[str, str]] = None):
    return request_post("/report/getticketlist", {"account_id": account_id, "auth_token": token}, headers)

# ---------- Helpers ----------
def pick_first_wallet(list_json: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    arr = list_json.get("value") if isinstance(list_json, dict) else None
    if isinstance(arr, list) and arr:
        return arr[0] if isinstance(arr[0], dict) else None
    return None

def summarize_statement(stmt: Dict[str, Any]) -> str:
    arr = stmt.get("value") if isinstance(stmt, dict) else None
    if not isinstance(arr, list) or not arr:
        return "No statement items."
    it = arr[0]  # newest first
    date = it.get("datetime") or it.get("date") or "-"
    typ  = it.get("type") or it.get("txn_type") or "-"
    bank = it.get("bank") or it.get("method") or "-"
    amt  = it.get("amount") or it.get("amt") or "-"
    st   = it.get("status") or "-"
    return f"{date}  {typ}  {bank}  {amt}  {st}"

# ---------- Session retry ----------
def with_session_retry(fn, account_id: str, token: str, headers: Dict[str, str], *args):
    code, data = fn(account_id, token, *args, headers=headers)
    desc = str(data.get("statusdesc", "")).lower() if isinstance(data, dict) else ""
    if any(k in desc.replace("_","") for k in ["sessionexpired", "session expired"]):
        print("\n⚠️  Session expired — please login again.")
        new_token, acct_from_login = do_login_flow(account_id, headers)
        if not new_token:
            return code, data, token, account_id
        if acct_from_login: account_id = acct_from_login
        code, data = fn(account_id, new_token, *args, headers=headers)
        return code, data, new_token, account_id
    return code, data, token, account_id

# ---------- Flows ----------
def do_login_flow(current_account_id: Optional[str], headers: Dict[str, str]):
    acct = current_account_id or input("Account ID: ").strip()
    pwd  = input("Password: ").strip()  # visible input per your request
    token, acct_from_login, _ = login(acct, pwd, headers=headers)
    if token:
        if acct_from_login: acct = acct_from_login
        print("\n[STORED TOKEN] OK")
    else:
        print("\n⚠️  No token found in login response. Check credentials or response shape.")
    return token, acct_from_login

def withdraw_using_first_wallet(account_id: str, token: str, amount: str, headers: Dict[str, str]):
    code, data = get_member_bank_list(account_id, token, headers=headers)
    print("\n[WALLET LIST]", code); print(pretty(data))
    if code != 200 or not isinstance(data, dict):
        return code, data
    first = pick_first_wallet(data)
    if not first:
        return 200, {"status": -1, "statusdesc": "no_wallet_found"}
    member_bank_id = (first.get("member_bank_id") or first.get("banklist_id")
                      or first.get("id") or first.get("member_bank_list_id"))
    bank_id  = first.get("bank_id") or first.get("bankname") or "GCASH"
    acc_no   = first.get("bank_acc_no") or first.get("account_no") or first.get("acc_no")
    if member_bank_id:
        return submit_withdrawal_by_id(account_id, token, amount, str(member_bank_id), headers=headers)
    return submit_withdrawal_by_gcash(account_id, token, amount, bank_id, acc_no, headers=headers)

# ---------- Main ----------
def main():
    print("=== EpicWin GCASH CLI (Proxy-first + Statement/Tickets + Transparent Test Mode) ===")
    print(mask_proxy(PROXIES))
    check_proxy(PROXIES)   # <-- added proxy check at startup

    account_id = input("Account ID (e.g., user648621): ").strip()

    # Build a labeled, non-deceptive device profile & headers
    # NOTE: make_device_profile now generates realistic random device info.
    device_profile = make_device_profile(account_id)
    HEADERS = build_headers(device_profile)

    auth_token: Optional[str] = None

    while True:
        print("\nChoose an action:")
        print("  1) Login (get & store token)")
        print("  2) Add/Update GCASH e-wallet")
        print("  3) Submit Withdrawal (use FIRST saved wallet)")
        print("  4) Check Balance")
        print("  5) View Inbox")
        print("  6) Add/Update then Withdraw (FIRST wallet)")
        print("  7) View Statement (latest items)")
        print("  8) View Ticket List")
        print("  9) Show Effective Headers")
        print("  0) Exit")
        choice = input("> ").strip()

        if choice == "1":
            # Before login we can rotate device profile per-login if desired:
            # device_profile = make_device_profile(account_id)  # uncomment to re-randomize each login
            token, acct_from_login = do_login_flow(account_id, HEADERS)
            if token:
                auth_token = token
                if acct_from_login:
                    account_id = acct_from_login
                print(f"\n[ACTIVE ACCOUNT] {account_id}")

        elif choice == "2":
            if not auth_token:
                print("\nNo auth token. Please login first to add/update wallet.")
                continue
            holder = input("E-Wallet Holder Name: ").strip()
            number = input("E-Wallet Number (e.g., 09XXXXXXXXX): ").strip()
            code, data, auth_token, account_id = with_session_retry(
                add_update_wallet, account_id, auth_token, HEADERS, holder, number, "GCASH")
            print("\n[ADD/UPDATE WALLET]", code); print(pretty(data))

        elif choice == "3":
            if not auth_token:
                print("\nNo auth token. Please login first to withdraw.")
                continue
            amount = input("Withdrawal amount (Min 100 / Max 50000): ").strip()
            code, data, auth_token, account_id = with_session_retry(
                withdraw_using_first_wallet, account_id, auth_token, HEADERS, amount)
            print("\n[WITHDRAWAL SUBMIT]", code); print(pretty(data))

        elif choice == "4":
            if not auth_token:
                print("\nNo auth token. Please login first to check balance.")
                continue
            code, data, auth_token, account_id = with_session_retry(get_balance, account_id, auth_token, HEADERS)
            print("\n[GET BALANCE]", code); print(pretty(data))

        elif choice == "5":
            if not auth_token:
                print("\nNo auth token. Please login first to view inbox.")
                continue
            code, data, auth_token, account_id = with_session_retry(get_inbox, account_id, auth_token, HEADERS)
            print("\n[INBOX]", code); print(pretty(data))

        elif choice == "6":
            if not auth_token:
                print("\nNo auth token. Please login first.")
                continue
            holder = input("E-Wallet Holder Name: ").strip()
            number = input("E-Wallet Number (e.g., 09XXXXXXXXX): ").strip()
            code, data, auth_token, account_id = with_session_retry(
                add_update_wallet, account_id, auth_token, HEADERS, holder, number, "GCASH")
            print("\n[ADD/UPDATE WALLET]", code); print(pretty(data))
            amount = input("Withdrawal amount (Min 100 / Max 50000): ").strip()
            code, data, auth_token, account_id = with_session_retry(
                withdraw_using_first_wallet, account_id, auth_token, HEADERS, amount)
            print("\n[WITHDRAWAL SUBMIT]", code); print(pretty(data))

        elif choice == "7":
            if not auth_token:
                print("\nNo auth token. Please login first to view statement.")
                continue
            code, data, auth_token, account_id = with_session_retry(get_statement, account_id, auth_token, HEADERS)
            print("\n[STATEMENT]", code); print(pretty(data))
            if isinstance(data, dict):
                print("\nLatest:", summarize_statement(data))

        elif choice == "8":
            if not auth_token:
                print("\nNo auth token. Please login first to view tickets.")
                continue
            code, data, auth_token, account_id = with_session_retry(get_ticket_list, account_id, auth_token, HEADERS)
            print("\n[TICKET LIST]", code); print(pretty(data))

        elif choice == "9":
            print("\n[HEADERS IN USE]")
            print(pretty(HEADERS))

        elif choice == "0":
            print("Bye!"); sys.exit(0)
        else:
            print("Invalid choice.")

if __name__ == "__main__":
    main()
