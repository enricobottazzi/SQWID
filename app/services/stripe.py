"""Stripe payment verification. Stubbed for now — always succeeds."""


async def verify_checkout_session(session_id: str) -> bool:
    """Verify a Stripe Checkout session has been paid.

    Stub: always returns True. Replace with real Stripe API call later.
    """
    return True
