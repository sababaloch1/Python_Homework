"""ui/pages_public/login.py - Login page.

Form: email, password, "Log in" button.
Calls POST /auth/login via ui/api_client.py using form-encoded data.
On success: stores token, email, and decoded role via ui/auth_state.py and navigates to Dashboard.
Handles:
- Wrong credentials (HTTP 401: "Incorrect email or password")
- Inactive/locked account or other errors
- Unreachable API
Never stores the password in state or logs.
Links to Sign up.
"""

import streamlit as st

from ui.theme import apply_theme, current_mode
from ui.api_client import api_post
from ui.auth_state import login, is_logged_in, decode_jwt_payload_unverified


def render_login_page(navigate_to=None):
    apply_theme()
    mode = current_mode()
    is_dark = mode == "dark"

    card_bg = "#141414" if is_dark else "#fcfcfc"
    card_border = "#262626" if is_dark else "#e5e5e5"
    subtext_color = "#999999" if is_dark else "#555555"

    # Back button
    if st.button("← Back to Home", key="login_back_home_btn"):
        if navigate_to:
            navigate_to("Home")
        else:
            st.session_state["target_page"] = "Home"
            st.rerun()

    st.write("")

    # Centered container layout
    _, col_center, _ = st.columns([1, 2, 1])

    with col_center:
        st.markdown(
            f"""
            <div style="background-color: {card_bg}; border: 1px solid {card_border}; border-radius: 8px; padding: 2rem; margin-top: 1rem;">
                <h2 style="margin-top: 0; margin-bottom: 0.25rem;">Log In to CarbonLens</h2>
                <p style="color: {subtext_color}; font-size: 0.95rem; margin-bottom: 1.5rem;">Enter your corporate credentials to access your organization's carbon accounting dashboard.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

        with st.form("login_form", clear_on_submit=False):
            email = st.text_input("Email", placeholder="name@company.com").strip()
            password = st.text_input("Password", type="password", placeholder="••••••••")

            submit = st.form_submit_button("Log In", use_container_width=True)

            if submit:
                if not email or not password:
                    st.error("Please enter both email and password.")
                else:
                    # OAuth2PasswordRequestForm expects username and password as form data
                    form_data = {"username": email, "password": password}
                    with st.spinner("Authenticating..."):
                        ok, response = api_post("auth/login", form_data=form_data)

                    if ok and isinstance(response, dict) and "access_token" in response:
                        token = response["access_token"]
                        payload = decode_jwt_payload_unverified(token)
                        user_role = payload.get("role", "contributor")
                        login(token=token, email=email, role=user_role)
                        st.success("Login successful! Redirecting to Dashboard...")
                        if navigate_to:
                            navigate_to("Dashboard")
                        else:
                            st.session_state["target_page"] = "Dashboard"
                            st.rerun()
                    else:
                        detail = ""
                        if isinstance(response, dict):
                            detail = response.get("detail", "")
                        if "incorrect" in detail.lower() or "unauthorized" in detail.lower():
                            st.error("Incorrect email or password. Please try again.")
                        elif "inactive" in detail.lower():
                            st.error("This account is inactive. Please contact your organization administrator.")
                        elif "not reachable" in detail.lower():
                            st.error(f"Cannot connect to the server: {detail}")
                        else:
                            st.error(f"Login failed: {detail or 'Please check your credentials.'}")

        st.markdown(
            f"""
            <div style="text-align: center; margin-top: 1.5rem; color: {subtext_color}; font-size: 0.9rem;">
                Don't have an account?
            </div>
            """,
            unsafe_allow_html=True,
        )
        if st.button("Create an Account (Sign Up)", use_container_width=True, key="login_to_signup_btn"):
            if navigate_to:
                navigate_to("Sign Up")
            else:
                st.session_state["target_page"] = "Sign Up"
                st.rerun()


if __name__ == "__main__":
    st.set_page_config(page_title="Login - CarbonLens", page_icon="🌍")
    render_login_page()
