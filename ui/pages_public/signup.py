"""ui/pages_public/signup.py - Organization & Admin Sign-Up page.

Form: Full name, Organisation name, Email, Password, Confirm password.
Validation in UI first:
- All fields required
- Valid email format (basic regex / structure)
- Password length >= 6
- Passwords must match
Calls POST /auth/register with {full_name, org_name, email, password}.
Handles:
- "Email already registered" (HTTP 400) with a friendly notification.
- Automatic login upon successful registration (POST /auth/login)
- Welcome banner explaining the organization is empty and guiding where to add the first data.
- Link to Login page.
"""

import re
import streamlit as st

from ui.theme import apply_theme, current_mode
from ui.api_client import api_post
from ui.auth_state import login, decode_jwt_payload_unverified


EMAIL_REGEX = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


def is_valid_email(email: str) -> bool:
    return bool(re.match(EMAIL_REGEX, email))


def render_signup_page(navigate_to=None):
    apply_theme()
    mode = current_mode()
    is_dark = mode == "dark"

    card_bg = "#141414" if is_dark else "#fcfcfc"
    card_border = "#262626" if is_dark else "#e5e5e5"
    subtext_color = "#999999" if is_dark else "#555555"

    # Back button
    if st.button("← Back to Home", key="signup_back_home_btn"):
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
                <h2 style="margin-top: 0; margin-bottom: 0.25rem;">Create Your Organization</h2>
                <p style="color: {subtext_color}; font-size: 0.95rem; margin-bottom: 1.5rem;">Register a new organization and initialize your primary administrator account.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

        with st.form("signup_form", clear_on_submit=False):
            full_name = st.text_input("Full Name", placeholder="Jane Doe").strip()
            org_name = st.text_input("Organisation Name", placeholder="Acme Logistics GmbH").strip()
            email = st.text_input("Work Email", placeholder="jane@acme.com").strip()
            password = st.text_input("Password", type="password", placeholder="Min. 6 characters")
            confirm_password = st.text_input("Confirm Password", type="password", placeholder="Repeat password")

            submit = st.form_submit_button("Create Account & Organization", use_container_width=True)

            if submit:
                # 1. UI-level Validation
                if not full_name:
                    st.error("Please enter your full name.")
                elif not org_name:
                    st.error("Please enter your organisation name.")
                elif not email:
                    st.error("Please enter your email address.")
                elif not is_valid_email(email):
                    st.error("Please enter a valid email address (e.g., name@company.com).")
                elif len(password) < 6:
                    st.error("Password must be at least 6 characters long.")
                elif password != confirm_password:
                    st.error("Passwords do not match. Please re-enter them carefully.")
                else:
                    # 2. Call POST /auth/register
                    payload = {
                        "full_name": full_name,
                        "org_name": org_name,
                        "email": email,
                        "password": password,
                    }
                    with st.spinner("Creating your organization and account..."):
                        ok, response = api_post("auth/register", json_data=payload)

                    if ok:
                        # 3. Automatically log in the user
                        login_ok, login_resp = api_post(
                            "auth/login",
                            form_data={"username": email, "password": password},
                        )
                        if login_ok and isinstance(login_resp, dict) and "access_token" in login_resp:
                            token = login_resp["access_token"]
                            jwt_payload = decode_jwt_payload_unverified(token)
                            user_role = jwt_payload.get("role", "admin")
                            login(token=token, email=email, role=user_role)

                            st.session_state["just_registered"] = True
                            st.session_state["registered_org_name"] = org_name

                            st.success("Account created successfully!")
                            if navigate_to:
                                navigate_to("Dashboard")
                            else:
                                st.session_state["target_page"] = "Dashboard"
                                st.rerun()
                        else:
                            st.success("Registration complete! Please proceed to the login page.")
                            if navigate_to:
                                navigate_to("Login")
                            else:
                                st.session_state["target_page"] = "Login"
                                st.rerun()
                    else:
                        detail = ""
                        if isinstance(response, dict):
                            detail = response.get("detail", "")
                        if "already registered" in str(detail).lower():
                            st.error(f"The email '{email}' is already registered. Please log in or use another email.")
                        elif "not reachable" in str(detail).lower():
                            st.error(f"Cannot connect to the server: {detail}")
                        else:
                            st.error(f"Registration failed: {detail or 'Please check your information and try again.'}")

        st.markdown(
            f"""
            <div style="text-align: center; margin-top: 1.5rem; color: {subtext_color}; font-size: 0.9rem;">
                Already have an account?
            </div>
            """,
            unsafe_allow_html=True,
        )
        if st.button("Log In Instead", use_container_width=True, key="signup_to_login_btn"):
            if navigate_to:
                navigate_to("Login")
            else:
                st.session_state["target_page"] = "Login"
                st.rerun()


if __name__ == "__main__":
    st.set_page_config(page_title="Sign Up - CarbonLens", page_icon="🌍")
    render_signup_page()
