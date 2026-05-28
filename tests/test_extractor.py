from extractor import extract_policy_fields


def test_extracts_policy_number() -> None:
    fields = extract_policy_fields("POLICY NUMBER: VF99999990")

    assert fields["policy_number"] == "VF99999990"


def test_extracts_insured_name() -> None:
    text = "INSURED: LELAND STANFORD SEX AND AGE: MALE 35"

    fields = extract_policy_fields(text)

    assert fields["insured_name"] == "LELAND STANFORD"


def test_extracts_premium() -> None:
    text = "INITIAL MONTHLY PREMIUM: $36.00"

    fields = extract_policy_fields(text)

    assert fields["premium"] == {"interval": "MONTHLY", "amount": "$36.00"}


def test_extracts_effective_date() -> None:
    text = "POLICY DATE: MAY 1, 2008"

    fields = extract_policy_fields(text)

    assert fields["effective_date"] == "MAY 1, 2008"
