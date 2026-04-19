"""Constants for the Picnic Companion integration."""

from __future__ import annotations

from datetime import timedelta

DOMAIN = "picnic_fr"

# --- Config entry / data keys ----------------------------------------------
CONF_EMAIL = "email"
CONF_PASSWORD = "password"
CONF_AUTH_KEY = "auth_key"
CONF_COUNTRY = "country"
CONF_TOKEN_EXP = "token_exp"
CONF_TOKEN_IAT = "token_iat"

DEFAULT_COUNTRY = "FR"

# --- Coordinator ------------------------------------------------------------
HISTORY_REFRESH_INTERVAL = timedelta(hours=12)

CONF_POLL_INTERVAL = "poll_interval_minutes"
DEFAULT_POLL_INTERVAL_MIN = 5
MIN_POLL_INTERVAL_MIN = 1
MAX_POLL_INTERVAL_MIN = 60

# --- Token ------------------------------------------------------------------
TOKEN_LIFETIME_DAYS = 180  # Picnic JWT is ~180 days
TOKEN_RENEWAL_WARNING_DAYS = 7  # raise repair issue 7 days before expiry

# --- Services ---------------------------------------------------------------
SERVICE_PUSH_LIST = "push_list"
SERVICE_CLEAR_CART = "clear_cart"
SERVICE_BOOK_SLOT = "book_slot"
SERVICE_CHECKOUT = "checkout"
SERVICE_REFRESH_HISTORY = "refresh_history"

# --- Issue ids --------------------------------------------------------------
ISSUE_TOKEN_EXPIRING = "token_expiring"
ISSUE_TOKEN_EXPIRED = "token_expired"

# --- Coordinator data keys --------------------------------------------------
DATA_CART = "cart"
DATA_SLOT = "selected_slot"
DATA_SLOTS = "available_slots"
DATA_HISTORY = "history"
DATA_DELIVERIES = "deliveries"
DATA_SAVED_RECIPES = "saved_recipes"
DATA_ORDERED_RECIPES = "ordered_recipes"
DATA_CURRENT_DELIVERY = "current_delivery"
DATA_DELIVERY_POSITION = "delivery_position"

SERVICE_ADD_RECIPE = "add_recipe_to_cart"
