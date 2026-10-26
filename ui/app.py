import base64
import json
import os

import requests
import streamlit as st

# Docker Compose sets this to the internal API service name.
# Local Streamlit runs default to localhost.
API_URL = os.getenv("API_URL", "http://localhost:8000")

st.set_page_config(page_title="Zero-Trust RBAC RAG", page_icon="🛡️", layout="wide")


def decode_jwt_payload(token: str) -> dict:
    """Decode display-only JWT claims; the API remains the authorization boundary."""
    try:
        payload_part = token.split(".")[1]
        padded = payload_part + "=" * (-len(payload_part) % 4)
        decoded_bytes = base64.urlsafe_b64decode(padded)
        return json.loads(decoded_bytes)
    except (IndexError, ValueError, json.JSONDecodeError):
        return {}


if "token" not in st.session_state:
    st.session_state["token"] = None
if "messages" not in st.session_state:
    st.session_state["messages"] = []
if "user_info" not in st.session_state:
    st.session_state["user_info"] = None

with st.sidebar:
    st.title("🛡️ Zero-Trust RAG")

    if not st.session_state["token"]:
        st.subheader("Sign in")
        username = st.text_input("Username", placeholder="alice_eng")
        password = st.text_input("Password", type="password", placeholder="Your local demo password")

        if st.button("Log In"):
            if not username.strip() or not password:
                st.warning("Enter the username and password configured in your local .env file.")
            else:
                try:
                    response = requests.post(
                        f"{API_URL}/token",
                        data={"username": username.strip(), "password": password},
                        timeout=15,
                    )
                    if response.status_code == 200:
                        token = response.json()["access_token"]
                        st.session_state["token"] = token
                        st.session_state["username"] = username.strip()
                        # Claims are displayed for convenience only; API checks access.
                        payload = decode_jwt_payload(token)
                        st.session_state["user_info"] = {
                            "roles": payload.get("roles", []),
                            "clearance": payload.get("clearance", "N/A"),
                        }
                        st.success("Authenticated successfully.")
                        st.rerun()
                    else:
                        st.error("Sign-in failed. Check the username and local demo password.")
                except requests.RequestException:
                    st.error("Could not reach the API. Check that the Docker services are running.")
    else:
        st.success(f"Logged in as: **{st.session_state['username']}**")
        if st.session_state.get("user_info"):
            roles = st.session_state["user_info"].get("roles", [])
            clearance = st.session_state["user_info"].get("clearance", "N/A")
            roles_str = ", ".join(roles) if roles else "None"
            st.markdown(
                f"**Displayed Security Context**\n\n"
                f"- Role(s): {roles_str}\n"
                f"- Clearance Level: {clearance}"
            )
        if st.button("Log Out"):
            st.session_state["token"] = None
            st.session_state["messages"] = []
            st.session_state["user_info"] = None
            st.rerun()

st.title("Enterprise RBAC Knowledge Base")

if not st.session_state["token"]:
    st.info("Sign in using one of the local demo accounts configured in .env.")
else:
    tab1, tab2 = st.tabs(["💬 Knowledge Base Chat", "📤 Admin Document Upload"])

    with tab1:
        if "processing" not in st.session_state:
            st.session_state["processing"] = False
        for msg in st.session_state["messages"]:
            with st.chat_message(msg["role"]):
                st.write(msg["content"])
                if msg.get("sources"):
                    with st.expander("🔍 View Retrieved Sources"):
                        for source in msg["sources"]:
                            st.code(source, language="text")

        if not st.session_state["processing"]:
            if user_query := st.chat_input("Ask a question about internal policies..."):
                st.session_state["messages"].append({"role": "user", "content": user_query})
                st.session_state["processing"] = True
                st.rerun()
        else:
            headers = {"Authorization": f"Bearer {st.session_state['token']}"}
            last_query = st.session_state["messages"][-1]["content"]
            with st.chat_message("assistant"):
                with st.spinner("Retrieving authorized context and generating answer..."):
                    try:
                        response = requests.post(
                            f"{API_URL}/query",
                            json={"query": last_query},
                            headers=headers,
                            timeout=180,
                        )
                        if response.status_code == 200:
                            result = response.json()
                            answer = result["answer"]
                            sources = result.get("accessed_documents", [])
                            st.write(answer)
                            if sources:
                                with st.expander("🔍 View Retrieved Sources"):
                                    for source in sources:
                                        st.code(source, language="text")
                            else:
                                st.info("No authorized source documents were retrieved.")
                            st.session_state["messages"].append(
                                {"role": "assistant", "content": answer, "sources": sources}
                            )
                        else:
                            st.error(f"Query failed ({response.status_code}). Check the API logs.")
                    except requests.RequestException:
                        st.error("The API request failed. Check service health and logs.")
            st.session_state["processing"] = False
            st.rerun()

    with tab2:
        st.subheader("🔒 Document Ingestion Management")
        user_roles = st.session_state.get("user_info", {}).get("roles", [])
        if "admin" not in user_roles:
            st.error("Access denied: only an administrator may upload documents.")
        else:
            st.write("Upload a UTF-8 .txt or .md document (maximum 1 MiB).")
            uploaded_file = st.file_uploader("Select document", type=["txt", "md"])
            roles_input = st.text_input(
                "Target allowed roles (comma-separated)",
                value="engineering",
                help="Example: engineering,hr,executive",
            )
            clearance_input = st.number_input(
                "Required clearance level", min_value=1, max_value=5, value=1
            )
            if st.button("Index Document", type="primary"):
                if uploaded_file is None:
                    st.warning("Select a file first.")
                else:
                    headers = {"Authorization": f"Bearer {st.session_state['token']}"}
                    files = {"file": (
                        uploaded_file.name, uploaded_file.getvalue(), uploaded_file.type
                    )}
                    data = {
                        "target_roles": roles_input,
                        "clearance_level": str(clearance_input),
                    }
                    with st.spinner("Validating, storing, and indexing the document..."):
                        try:
                            response = requests.post(
                                f"{API_URL}/upload", files=files, data=data,
                                headers=headers, timeout=180,
                            )
                            if response.status_code == 200:
                                result = response.json()
                                st.success(
                                    f"Indexed {result['filename']} and updated the manifest."
                                )
                            else:
                                st.error(f"Upload failed ({response.status_code}): {response.text}")
                        except requests.RequestException:
                            st.error("The upload request failed. Check API logs.")
