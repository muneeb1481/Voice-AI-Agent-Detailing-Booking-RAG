from app.services.job_parser import parse_job_text


def test_heuristic_parses_freeform_note():
    text = "Alex\n+1234567890\nToyota Corolla\nTN 38103\ninterior exterior\n$200"
    result = parse_job_text(text)
    assert result["customer_name"] == "Alex"
    assert result["customer_phone"] == "+1234567890"
    assert result["vehicle"] == "Toyota Corolla"
    assert result["state"] == "TN"
    assert result["zip_code"] == "38103"
    assert result["price_cents"] == 20000


def test_heuristic_never_fabricates_missing_fields():
    result = parse_job_text("just a name with nothing else useful here")
    assert result["customer_phone"] is None
    assert result["price_cents"] is None
