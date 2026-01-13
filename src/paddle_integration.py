import streamlit as st
import streamlit.components.v1 as components
import os
import requests

# PADDLE CONFIGURATION
# Reads from Streamlit secrets first, then environment variables
def _get_paddle_config():
    """Get Paddle configuration from secrets or environment."""
    try:
        env = st.secrets.get("PADDLE_ENV", "live")
        client_token = st.secrets.get("PADDLE_CLIENT_TOKEN", "")
        api_key = st.secrets.get("PADDLE_API_KEY", "")
    except Exception:
        env = os.getenv("PADDLE_ENV", "live")
        client_token = os.getenv("PADDLE_CLIENT_TOKEN", "")
        api_key = os.getenv("PADDLE_API_KEY", "")
    return env, client_token, api_key

PADDLE_ENV, PADDLE_CLIENT_TOKEN, PADDLE_API_KEY = _get_paddle_config()

# Price IDs - read from secrets
def _get_price_ids():
    """Get Paddle price IDs from secrets or environment."""
    try:
        return {
            "basic": st.secrets.get("PADDLE_PRICE_BASIC", ""),
            "plus": st.secrets.get("PADDLE_PRICE_PLUS", ""),
            "pro": st.secrets.get("PADDLE_PRICE_PRO", ""),
        }
    except Exception:
        return {
            "basic": os.getenv("PADDLE_PRICE_BASIC", ""),
            "plus": os.getenv("PADDLE_PRICE_PLUS", ""),
            "pro": os.getenv("PADDLE_PRICE_PRO", ""),
        }

PADDLE_PRICES = _get_price_ids()

def init_paddle():
    """
    Injects the Paddle.js script into the Streamlit app.
    Call this once at the top of your app (e.g. in sidebar or main).
    """
    if not PADDLE_CLIENT_TOKEN:
        return  # Skip if not configured
        
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
                token: "{PADDLE_CLIENT_TOKEN}"
            }});
            console.log("Paddle initialized (env: {PADDLE_ENV})");
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
    
    # Ensure the Paddle script is loaded inside this component iframe and initialize it
    script_url = "https://sandbox-cdn.paddle.com/paddle/v2/paddle.js" if PADDLE_ENV == "sandbox" else "https://cdn.paddle.com/paddle/v2/paddle.js"

    html_code = f"""
    <style>
        .paddle-btn {{
            background-color: #2563EB;
            color: white;
            padding: 12px 24px;
            border-radius: 12px;
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
    <!-- Load Paddle inside this iframe so window.Paddle is available to the button code -->
    <script src="{script_url}"></script>
    <script type="text/javascript">
        if (window.Paddle) {{
            try {{
                Paddle.Initialize({{ token: "{PADDLE_CLIENT_TOKEN}" }});
            }} catch(e) {{
                console.warn('Paddle Initialize failed:', e);
            }}
        }}
        function openCheckout() {{
            if (window.Paddle) {{
                Paddle.Checkout.open({{
                    items: [{{ priceId: '{price_id}', quantity: 1 }}],
                    customer: {{
                        {email_js}
                    }},
                    settings: {{
                        successUrl: window.location.href
                    }}
                }});
            }} else {{
                console.error("Paddle not loaded yet");
            }}
        }}
    </script>
    <button class="paddle-btn" onclick="openCheckout()">{button_text}</button>
    """
    
    # Height needs to be large enough for the button
    components.html(html_code, height=60)


def get_subscription_status(customer_email: str) -> dict | None:
    """
    Check if a customer has an active subscription via Paddle API.
    Returns subscription data or None if no active subscription.
    """
    if not PADDLE_API_KEY:
        return None
    
    base_url = "https://api.paddle.com" if PADDLE_ENV == "live" else "https://sandbox-api.paddle.com"
    
    headers = {
        "Authorization": f"Bearer {PADDLE_API_KEY}",
        "Content-Type": "application/json",
    }
    
    try:
        # Search for subscriptions by customer email
        response = requests.get(
            f"{base_url}/subscriptions",
            headers=headers,
            params={"status": "active"},
            timeout=10,
        )
        
        if response.status_code == 200:
            data = response.json()
            subscriptions = data.get("data", [])
            
            # Find subscription matching customer email
            for sub in subscriptions:
                if sub.get("customer", {}).get("email", "").lower() == customer_email.lower():
                    return {
                        "subscription_id": sub.get("id"),
                        "status": sub.get("status"),
                        "plan_id": sub.get("items", [{}])[0].get("price", {}).get("id"),
                        "next_billing": sub.get("next_billed_at"),
                    }
        return None
    except Exception as e:
        print(f"Paddle API error: {e}")
        return None


def get_user_tier(customer_email: str) -> str:
    """
    Get the user's current subscription tier.
    Returns: "free", "basic", "plus", or "pro"
    """
    if not customer_email:
        return "free"
    
    sub = get_subscription_status(customer_email)
    if not sub:
        return "free"
    
    plan_id = sub.get("plan_id", "")
    
    # Map price IDs to tier names
    if plan_id == PADDLE_PRICES.get("pro"):
        return "pro"
    elif plan_id == PADDLE_PRICES.get("plus"):
        return "plus"
    elif plan_id == PADDLE_PRICES.get("basic"):
        return "basic"
    
    return "free"


def render_upgrade_button(tier: str, customer_email: str = None) -> None:
    """
    Render an upgrade button for a specific tier.
    """
    price_id = PADDLE_PRICES.get(tier, "")
    
    if not price_id:
        st.warning(f"Price ID not configured for {tier} tier")
        return
    
    tier_names = {
        "basic": "Basic ($9/mo)",
        "plus": "Plus ($19/mo)", 
        "pro": "Pro ($29/mo)",
    }
    
    button_text = f"Upgrade to {tier_names.get(tier, tier.title())}"
    render_checkout_button(price_id, customer_email, button_text)
