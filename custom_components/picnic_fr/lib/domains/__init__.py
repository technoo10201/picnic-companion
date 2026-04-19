from .auth import AuthDomain
from .catalog import CatalogDomain
from .cart import CartDomain
from .delivery import DeliveryDomain
from .user import UserDomain
from .payment import PaymentDomain
from .recipes import RecipesDomain
from .messages import MessagesDomain
from .consent import ConsentDomain
from .static_content import StaticContentDomain

__all__ = [
    "AuthDomain",
    "CatalogDomain",
    "CartDomain",
    "DeliveryDomain",
    "UserDomain",
    "PaymentDomain",
    "RecipesDomain",
    "MessagesDomain",
    "ConsentDomain",
    "StaticContentDomain",
]
