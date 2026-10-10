import base64
import json
import requests
import streamlit as st
import os

# Fetch API URL from environment variable; default to service name on Docker network
API_URL = os.getenv("API_URL", "http://rag_api:8000")

st.set_page_config(page_title="Zero-Trust RBAC RAG", page_icon="🛡️", layout="wide")


# --- HELPER FUNCTION: DECODE JWT ---
def decode_jwt_payload(token: str) -> dict:
    """Decodes JWT payload without external libraries to extract user metadata."""
    try:
        payload_part = token.split(".")[1]
        padded = payload_part + "=" * (-len(payload_part) % 4)
        decoded_bytes = base64.urlsafe_b64decode(padded)
        return json.loads(decoded_bytes)
    except Exception:
        return {}


# Initialize Session State
if "token" not in st.session_state:
    st.session_state["token"] = None
if "messages" not in st.session_state:
    st.session_state["messages"] = []
if "user_info" not in st.session_state:
    st.session_state["user_info"] = None

# --- SIDEBAR: AUTHENTICATION ---
with st.sidebar:
    st.title("🛡️ Zero-Trust RAG")

    if not st.session_state["token"]:
        st.subheader("Login")
        username = st.text_input("Username", value="admin_user")
        password = st.text_input("Password", type="password", value="password123")

        if st.button("Log In"):
            response = requests.post(
                f"{API_URL}/token",
                data={"username": username, "password": password},
            )
            if response.status_code == 200:
                token_data = response.json()
                token = token_data["access_token"]

                st.session_state["token"] = token
                st.session_state["username"] = username

                # Extract and store role & clearance level from JWT token
                payload = decode_jwt_payload(token)
                st.session_state["user_info"] = {
                    "roles": payload.get("roles", []),
                    "clearance": payload.get("clearance", "N/A"),
                }

                st.success("Authenticated successfully!")
                st.rerun()
            else:
                st.error("Invalid username or password.")
    else:
        st.success(f"Logged in as: **{st.session_state['username']}**")

        if st.session_state.get("user_info"):
            roles = st.session_state["user_info"].get("roles", [])
            clearance = st.session_state["user_info"].get("clearance", "N/A")
            roles_str = ", ".join(roles) if roles else "None"

            st.markdown(
                f"""
            **Active Security Context:**
            - 🎭 **Role(s):** `{roles_str}`
            - 🔑 **Clearance Level:** `{clearance}`
            """
            )

        if st.button("Log Out"):
            st.session_state["token"] = None
            st.session_state["messages"] = []
            st.session_state["user_info"] = None
            st.rerun()

# --- MAIN INTERFACE ---
st.title("Enterprise RBAC Knowledge Base")

if not st.session_state["token"]:
    st.info("👈 Please log in via the sidebar to access the platform.")
else:
    tab1, tab2 = st.tabs(["💬 Knowledge Base Chat", "📤 Admin Document Upload"])

    # ==========================================
    # TAB 1: CHAT INTERFACE
    # ==========================================
    with tab1:
        # Initialize processing state
        if "processing" not in st.session_state:
            st.session_state["processing"] = False

        # 1. Render all existing messages in chat history
        for msg in st.session_state["messages"]:
            with st.chat_message(msg["role"]):
                st.write(msg["content"])
                if "sources" in msg and msg["sources"]:
                    with st.expander("🔍 View Retrieved Sources (RBAC Filtered)"):
                        for src in msg["sources"]:
                            st.code(src, language="text")

        # 2. Render input box ONLY when not processing a query
        if not st.session_state["processing"]:
            if user_query := st.chat_input("Ask a question about internal policies..."):
                # Append query to state and set processing state
                st.session_state["messages"].append(
                    {"role": "user", "content": user_query}
                )
                st.session_state["processing"] = True
                st.rerun()

        # 3. Handle processing state: input box is hidden, show loading spinner & call API
        else:
            headers = {"Authorization": f"Bearer {st.session_state['token']}"}
            last_query = st.session_state["messages"][-1]["content"]

            with st.chat_message("assistant"):
                with st.spinner("Retrieving authorized context & generating answer..."):
                    res = requests.post(
                        f"{API_URL}/query",
                        json={"query": last_query},
                        headers=headers,
                    )

                    if res.status_code == 200:
                        data = res.json()
                        answer = data["answer"]
                        sources = data.get("accessed_documents", [])

                        st.write(answer)
                        if sources:
                            with st.expander(
                                    "🔍 View Retrieved Sources (RBAC Filtered)"
                            ):
                                for src in sources:
                                    st.code(src, language="text")
                        else:
                            st.warning(
                                "⚠️ No documents retrieved (either non-existent or restricted by clearance level)."
                            )

                        # Save response to history
                        st.session_state["messages"].append(
                            {
                                "role": "assistant",
                                "content": answer,
                                "sources": sources,
                            }
                        )
                    else:
                        st.error(f"Error {res.status_code}: Could not fetch response.")

            # Reset processing state and rerun to restore the input box at the bottom
            st.session_state["processing"] = False
            st.rerun()

    # ==========================================
    # TAB 2: ADMIN DOCUMENT UPLOAD
    # ==========================================
    with tab2:
        st.subheader("🔒 Enterprise Document Ingestion Management")

        user_roles = st.session_state.get("user_info", {}).get("roles", [])

        if "admin" not in user_roles:
            st.error(
                "⛔ Access Denied: Only administrators can upload documents and assign target RBAC policies."
            )
        else:
            st.write(
                "Upload document `.txt` or `.md` files to update the manifest and auto-index into Qdrant."
            )

            uploaded_file = st.file_uploader(
                "Select Document File", type=["txt", "md"]
            )
            target_roles_input = st.text_input(
                "Target Allowed Roles (comma-separated)",
                value="engineering",
                help="e.g. engineering, hr, executive",
            )
            clearance_input = st.number_input(
                "Required Clearance Level",
                min_value=1,
                max_value=5,
                value=1,
            )

            if st.button("Index Document to Vector Store", type="primary"):
                if uploaded_file is None:
                    st.warning("Please select a file first.")
                else:
                    headers = {
                        "Authorization": f"Bearer {st.session_state['token']}"
                    }
                    files = {
                        "file": (
                            uploaded_file.name,
                            uploaded_file.getvalue(),
                            uploaded_file.type,
                        )
                    }
                    data_payload = {
                        "target_roles": target_roles_input,
                        "clearance_level": str(clearance_input),
                    }

                    with st.spinner(
                        "Updating manifest and processing chunks into Qdrant..."
                    ):
                        res = requests.post(
                            f"{API_URL}/upload",
                            files=files,
                            data=data_payload,
                            headers=headers,
                        )

                        if res.status_code == 200:
                            res_json = res.json()
                            st.success(
                                f"Successfully indexed **{res_json['filename']}** and updated `manifest.json`!"
                            )
                        else:
                            st.error(f"Upload failed ({res.status_code}): {res.text}")