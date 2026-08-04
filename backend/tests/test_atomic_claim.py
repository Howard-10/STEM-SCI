import pytest
from pydantic import ValidationError

from stem_sci.core.claims import AtomicClaim, ClaimType


def test_atomic_claim_accepts_one_type_and_rejects_composite_type() -> None:
    claim = AtomicClaim(claim_id="claim-1", text="A result.", claim_type=ClaimType.RESULT)
    assert claim.claim_type is ClaimType.RESULT
    with pytest.raises(ValidationError):
        AtomicClaim(claim_id="claim-2", text="Two claims.", claim_type="RESULT+METHOD")
