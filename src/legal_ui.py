import streamlit as st

def render_terms_of_service_page():
    st.title("Terms of Service")
    st.markdown("""
These Terms of Service govern your use of **ChessAnalyzerV1**, operated by us.  
By accessing or using the Service, you agree to these Terms.  
**If you do not agree, do not use the Service.**

### 1. The Service
**ChessAnalyzerV1** provides chess game analysis, coaching insights, and related tools powered by chess engines and AI models.
- The Service is provided for **educational and entertainment purposes only**.
- We do not guarantee rating improvement, game outcomes, or accuracy of analysis.

### 2. Accounts & Eligibility
- You must be legally allowed to enter into agreements in your country to use the Service.
- If you are under 18, you must have permission from a parent or legal guardian.
- You are responsible for maintaining the confidentiality of your account and activity.
- We may suspend or terminate accounts that violate these Terms.

### 3. Subscriptions & Payments
- Some features require a paid **subscription**.
- Payments are processed by our payment provider (e.g. **Paddle**), not directly by us.
- Prices, limits (games analyzed, depth, reports), and plans are described on our website.
- Subscriptions renew automatically unless canceled.
- Refunds are handled according to our payment provider’s refund policy.
- We reserve the right to change pricing or plan limits, with reasonable notice.

### 4. Usage Limits & Fair Use
Each plan has usage limits (e.g. number of games, analysis depth, reports per month).
You agree not to:
- Abuse the system (e.g. automated scraping, excessive batch submissions)
- Attempt to bypass plan limits
- Reverse engineer or resell the Service

We may restrict usage if abuse is detected.

### 5. Chess Data & Content
- You retain ownership of your chess games and uploaded data.
- By using the Service, you grant us permission to process this data solely to provide analysis and improve the Service.
- We do **not** sell your personal chess data.
- Publicly available games (e.g. from Lichess or Chess.com) may be analyzed at your request.
""")
