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


def render_privacy_policy_page():
    st.title("Privacy Policy")
    st.markdown("""
**Effective Date:** January 2026

This Privacy Policy explains how **we** collect, use, and protect your information when you use **ChessAnalyzerV1**.

### 1. Information We Collect
- **Account Information:** If you sign up, we collect your email address and authentication details.
- **Chess Data:** We process PGN files and username data you provide to analyze games.
- **Usage Data:** We collect anonymous metrics on how you use the Service (e.g., features used, errors encountered).
- **Payment Information:** We do **not** store your credit card details. All payments are processed by our secure provider (e.g., Paddle).

### 2. How We Use Your Information
- To provide the chess analysis and coaching features.
- To improve the performance and accuracy of our engines.
- To communicate with you regarding your account or updates to the Service.

### 3. Data Sharing
- We do **not** sell your personal data to third parties.
- We may share data with service providers (e.g., hosting, payment) solely to operate the Service.
- We may disclose information if required by law.

### 4. Data Security
We implement reasonable security measures to protect your data. However, no method of transmission over the Internet is 100% secure.

### 5. Your Rights
- You can request deletion of your account and associated data by contacting us.
- You can export your analysis data at any time.

### 6. Contact Us
If you have questions about this policy, please contact us at: **orvarsv@icloud.com**
""")


def render_refund_policy_page():
    st.title("Refund Policy")
    st.markdown("""
**All sales are final.**

### No Refunds
Because **ChessAnalyzerV1** offers digital goods and immediate access to server-intensive analysis resources, **we do not offer refunds** for subscriptions or one-time purchases once the service has been used or the billing cycle has started.

### Cancel Anytime
You may cancel your subscription at any time to prevent future billing. Your access will continue until the end of your current billing period.

### Exceptional Circumstances
In the event of a technical error (e.g., double billing) attributed to our systems, please contact support at **orvarsv@icloud.com** to resolve the issue. We resolve these specific cases at our sole discretion.
""")
