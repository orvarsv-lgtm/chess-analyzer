"""
Mobile device detection and responsive UI utilities.

Provides centralized mobile detection and responsive layout helpers
for use across the entire Streamlit application.
"""

from typing import Optional
import streamlit as st


MOBILE_BREAKPOINT = 768  # Screen width threshold in pixels
TABLET_BREAKPOINT = 1024  # Tablet threshold


def detect_device_type() -> str:
    """
    Detect device type: 'mobile', 'tablet', or 'desktop'.
    
    Returns:
        str: One of 'mobile', 'tablet', or 'desktop'
    """
    if "device_type" not in st.session_state:
        st.session_state["device_type"] = _infer_device_type()
    return st.session_state["device_type"]


def _infer_device_type() -> str:
    """Infer device type using multiple heuristics."""
    # Try to get screen width via JavaScript injection
    screen_width = _get_screen_width()
    
    if screen_width:
        if screen_width < MOBILE_BREAKPOINT:
            return "mobile"
        elif screen_width < TABLET_BREAKPOINT:
            return "tablet"
        else:
            return "desktop"
    
    # Fallback: Use user agent (less reliable)
    return _detect_from_user_agent()


def _get_screen_width() -> Optional[int]:
    """Get screen width via JavaScript."""
    if "screen_width" not in st.session_state:
        # Inject JavaScript to capture screen width
        js_code = """
        <script>
        if (window.innerWidth) {
            window.streamlitScreenWidth = window.innerWidth;
        }
        </script>
        """
        st.markdown(js_code, unsafe_allow_html=True)
    
    return st.session_state.get("screen_width")


def _detect_from_user_agent() -> str:
    """Detect device type from user agent string."""
    user_agent = st.query_params.get("user_agent", "").lower()
    
    mobile_keywords = ["mobile", "android", "iphone", "ipod", "webos", "blackberry", "windows phone"]
    tablet_keywords = ["ipad", "tablet", "kindle", "nexus 7", "nexus 10", "xoom"]
    
    if any(keyword in user_agent for keyword in mobile_keywords):
        return "mobile"
    elif any(keyword in user_agent for keyword in tablet_keywords):
        return "tablet"
    else:
        return "desktop"


def is_mobile() -> bool:
    """Check if user is on mobile device."""
    return detect_device_type() == "mobile"


def is_tablet() -> bool:
    """Check if user is on tablet device."""
    return detect_device_type() == "tablet"


def is_desktop() -> bool:
    """Check if user is on desktop device."""
    return detect_device_type() == "desktop"


def apply_mobile_layout() -> None:
    """Apply mobile-friendly CSS and configuration."""
    if not is_mobile():
        return
    
    # Hide sidebar on mobile for more screen space
    st.markdown(
        """
        <style>
            [data-testid="collapsedControl"] {
                display: none;
            }
            section[data-testid="stSidebar"] {
                display: none;
            }
            @media (max-width: 768px) {
                .main {
                    margin: 0;
                    padding: 0;
                }
                .stMetric {
                    font-size: 12px;
                }
                button {
                    width: 100%;
                    padding: 12px 4px;
                    font-size: 14px;
                }
            }
        </style>
        """,
        unsafe_allow_html=True,
    )


def get_board_size() -> int:
    """Get optimal chessboard size for device."""
    device = detect_device_type()
    if device == "mobile":
        return 300  # Mobile: smaller board
    elif device == "tablet":
        return 400  # Tablet: medium board
    else:
        return 500  # Desktop: full size


def get_column_layout() -> tuple[int, ...]:
    """Get optimal column layout for device."""
    device = detect_device_type()
    if device == "mobile":
        return (1,)  # Mobile: single column
    elif device == "tablet":
        return (1, 1)  # Tablet: 2 columns
    else:
        return (2, 1)  # Desktop: 2-column with sidebar


def render_mobile_controls() -> None:
    """Render device type and settings info (for debugging)."""
    if not st.session_state.get("_show_device_debug", False):
        return
    
    device = detect_device_type()
    st.caption(f"📱 Device: {device.upper()}")


def create_mobile_friendly_button(label: str, key: str, help_text: Optional[str] = None) -> bool:
    """Create a button optimized for mobile."""
    return st.button(
        label,
        key=key,
        help=help_text,
        use_container_width=is_mobile() or is_tablet(),
    )


def create_mobile_friendly_columns() -> list:
    """Create columns optimized for device."""
    layout = get_column_layout()
    return st.columns(layout)


def format_for_mobile(text: str, max_length: int = 50) -> str:
    """Truncate text for mobile if needed."""
    if not is_mobile():
        return text
    if len(text) > max_length:
        return text[:max_length - 3] + "..."
    return text
