from scripts.verify_news_context_offline_replay import load_json, self_test
from scripts.verify_news_context_offline_replay import CONTRACT_PATH, FIXTURE_PATH


def test_news_context_offline_replay_contract() -> None:
    contract = load_json(CONTRACT_PATH)
    fixture = load_json(FIXTURE_PATH)
    self_test(contract, fixture)
