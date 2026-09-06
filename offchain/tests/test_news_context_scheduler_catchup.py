from scripts.verify_news_context_scheduler_catchup import CONTRACT_PATH, FIXTURE_PATH
from scripts.verify_news_context_scheduler_catchup import load_json, self_test


def test_news_context_scheduler_catchup_contract() -> None:
    contract = load_json(CONTRACT_PATH)
    fixture = load_json(FIXTURE_PATH)
    self_test(contract, fixture)
