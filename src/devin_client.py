import os
import sys
import time
import requests

API_BASE = "https://api.devin.ai/v1"


def devin_ui_url(session_id: str) -> str:
    sid = session_id.rsplit("/", 1)[-1]
    if sid.startswith("devin-"):
        sid = sid[len("devin-"):]
    return f"https://app.devin.ai/sessions/{sid}"


def _get_devin_headers():
    api_key = os.getenv("DEVIN_API_KEY")
    if not api_key:
        print("DEVIN_API_KEY is missing. Please set it in your environment.")
        sys.exit(1)
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


def create_devin_session(prompt: str):
    url = f"{API_BASE}/sessions"
    headers = _get_devin_headers()
    resp = requests.post(url, headers=headers, json={"prompt": prompt}, timeout=60)
    if resp.status_code < 200 or resp.status_code >= 300:
        print("Devin session creation failed:", resp.status_code)
        print(resp.text)
        sys.exit(1)
    data = resp.json()
    session_id = data.get("session_id") or data.get("id")
    if not session_id:
        print("Devin response missing session_id.")
        print(data)
        sys.exit(1)
    return session_id


def send_devin_message(session_id: str, message: str):
    url = f"{API_BASE}/sessions/{session_id}/message"
    headers = _get_devin_headers()
    resp = requests.post(url, headers=headers, json={"message": message}, timeout=60)
    if resp.status_code < 200 or resp.status_code >= 300:
        print("Failed to send message to Devin:", resp.status_code)
        print(resp.text)
        sys.exit(1)
    return resp.json()


def poll_devin_session(
    session_id: str,
    max_wait: int = 300,
    validator=None,
    required_status: set[str] | None = None,
):
    api_url = f"{API_BASE}/sessions/{session_id}"
    headers = _get_devin_headers()

    start = time.time()
    backoff = 1
    target_status = required_status or {"finished", "blocked"}
    saw_working = False

    while True:
        resp = requests.get(api_url, headers=headers, timeout=60)
        if resp.status_code < 200 or resp.status_code >= 300:
            print("Devin session poll failed:", resp.status_code)
            print(resp.text)
            sys.exit(1)

        data = resp.json()
        status = data.get("status_enum")

        if status == "working":
            saw_working = True

        # print(f"Status after {backoff} seconds: ", status)
        if saw_working and status in target_status:
            final_resp = requests.get(api_url, headers=headers, timeout=60)
            if final_resp.status_code < 200 or final_resp.status_code >= 300:
                print("Devin final fetch failed:", final_resp.status_code)
                print(final_resp.text)
                sys.exit(1)
            final_data = final_resp.json()
            final_status = final_data.get("status_enum") or status
            so = final_data.get("structured_output")
            if validator and not validator(so):
                time.sleep(min(backoff, 30))
                backoff = min(30, backoff * 2)
                continue
            return final_status, final_data

        if time.time() - start > max_wait:
            print("Polling timed out. You can check the session here:")
            print(api_url)
            return "timeout", data

        time.sleep(min(backoff, 30))
        backoff *= 2
