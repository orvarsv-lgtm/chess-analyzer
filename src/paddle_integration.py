import streamlit as st
import streamlit.components.v1 as components
import os

# PADDLE CONFIGURATION
# You should set these in your .streamlit/secrets.toml or environment variables
PADDLE_ENV = os.getenv("PADDLE_ENV", "sandbox")  # "sandbox" or "production"
PADDLE_CLIENT_TOKEN = os.getenv("PADDLE_CLIENT_TOKEN", "")  # Your Client Side Token

def init_paddle():
    """
    Injects the Paddle.js script into the Streamlit app.
    Call this once at the top of your app (e.g. in sidebar or main).
    """
    if PADDLE_ENV == "sandbox":
        script_url = "https://sandbox-cdn.paddle.com/paddle/v2/paddle.js"
    else:
        script_url = "https://cdn.paddle.com/paddle/v2/paddle.js"

    # We use a hidden div to inject the script only once if possible, 
    # but Streamlit re-runs scripts, so we check existence in JS.
    html_code = f"""
    <div id="paddle-init-container" style="display:none;"></div>
    <script src="{script_url}"></script>
    <script type="text/javascript">
        if (window.Paddle) {{
            Paddle.Initialize({{ 
                token: "{PADDLE_CLIENT_TOKEN}",
                environment: "{PADDLE_ENV}"
            }});
            console.log("Paddle initialized");
        }}
    </script>
    """
    components.html(html_code, height=0, width=0)

def render_checkout_button(price_id: str, customer_email: str = None, button_text: str = "Subscribe Now"):
    """
    Renders a custom button that triggers the Paddle Checkout.
    """
    # Defensive coding for email
    email_js = f"email: '{customer_email}'," if customer_email else ""
    
    html_code = f"""
    <style>
        .paddle-btn {{
            background-color: #2563EB;
            color: white;
            padding: 12px 24px;
            border-radius: 6px;
            border: none;
            font-weight: 600;
            cursor: pointer;
            width: 100%;
            transition: background-color 0.2s;
            font-family: sans-serif;
            font-size: 16px;
        }}
        .paddle-btn:hover {{
            background-color: #1D4ED8;
        }}
    </style>
    <button class="paddle-btn" onclick="openCheckout()">{button_text}</button>
    
    <script type="text/javascript">
        function openCheckout() {{
            if (window.Paddle) {{
                Paddle.Checkout.open({{
                    items: [{{ priceId: '{price_id}', quantity: 1 }}],
                    customer: {{
                        {email_js}
                    }},
                    settings: {{
                        successUrl: window.location.href // Returns to app after success
                    }}
                }});
            }} else {{
                console.error("Paddle not loaded yet");
            }}
        }}
    </script>
    """
    
    # Height needs to be large enough for the button
    components.html(html_code, height=60)
