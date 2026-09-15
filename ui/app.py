import base64
import json
import requests
import streamlit as st

API_URL = "http://127.0.0.1:8000"

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


# Initialize Session State for JWT and User Info
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
        username = st.text_input("Username", value="alice_eng")
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

        # --- DISPLAY ACTIVE ROLE & CLEARANCE LEVEL ---
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

# --- MAIN CHAT INTERFACE ---
st.title("Enterprise RBAC Knowledge Base")

if not st.session_state["token"]:
    st.info("👈 Please log in via the sidebar to start asking questions.")
else:
    # Display previous messages
    for msg in st.session_state["messages"]:
        with st.chat_message(msg["role"]):
            st.write(msg["content"])
            if "sources" in msg and msg["sources"]:
                with st.expander("🔍 View Retrieved Sources (RBAC Filtered)"):
                    for src in msg["sources"]:
                        st.code(src, language="text")

    # User Input
    if user_query := st.chat_input("Ask a question about internal policies..."):
        # Append User Message
        st.session_state["messages"].append(
            {"role": "user", "content": user_query}
        )
        with st.chat_message("user"):
            st.write(user_query)

        # Call FastAPI Endpoint with Bearer Token
        headers = {"Authorization": f"Bearer {st.session_state['token']}"}

        with st.chat_message("assistant"):
            with st.spinner("Retrieving authorized context & generating answer..."):
                res = requests.post(
                    f"{API_URL}/query",
                    json={"query": user_query},
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

                    # Save to History
                    st.session_state["messages"].append(
                        {
                            "role": "assistant",
                            "content": answer,
                            "sources": sources,
                        }
                    )
                else:
                    st.error(f"Error {res.status_code}: Could not fetch response.")