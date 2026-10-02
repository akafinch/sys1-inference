"""The preset catalogue: three texts, each with one choice, one score and one noul preset."""

import json

import pytest

from app.main import CATALOGUE

# Laya reads one question as at most 1,024 tokens, and cuts a longer state from its end
# without saying so (https://huggingface.co/convaiinnovations/laya-typed-decisions).
# Measured on Laya, the densest state here (the invoice: numbers and ids) ran 2.2
# characters to a token, and a question with its options 35-80 tokens. 1,200 characters
# keeps a question near 800 tokens even with its 256-token budget for options full.
MAX_STATE_CHARS = 1200


def test_the_page_gets_three_texts_and_the_targets_without_addresses(client):
    served = client.get("/api/presets").json()

    assert [text["id"] for text in served["texts"]] == ["routing", "invoice", "guardrail"]
    assert set(served["targets"]) == {"diffusiongemma", "laya-gpu", "laya-cpu"}
    assert "openjev.test" not in json.dumps(served)
    for text in served["texts"]:
        assert {p["target"] for p in text["presets"]} <= set(served["targets"])


@pytest.mark.parametrize("text", CATALOGUE["texts"], ids=lambda text: text["id"])
def test_each_text_asks_one_question_of_each_type(text):
    assert sorted(p["type"] for p in text["presets"]) == ["choice", "noul", "score"]
    assert len({p["id"] for p in text["presets"]}) == 3


@pytest.mark.parametrize(
    "preset",
    [preset for text in CATALOGUE["texts"] for preset in text["presets"]],
    ids=lambda preset: preset["id"],
)
def test_each_intended_answer_is_one_its_question_allows(preset):
    question, intended = preset["question"], preset["intended"]
    assert question["type"] == preset["type"]
    if preset["type"] == "choice":
        assert 2 <= len(question["criteria"]) <= 20  # Laya: keep choices under about 20 options
        assert intended in question["criteria"]
    elif preset["type"] == "score":
        assert 2 <= len(question["criteria"]) <= 10  # OpenJev refuses an 11th level
        assert type(intended) is int and 0 <= intended < len(question["criteria"])
    else:
        assert type(intended) is bool


@pytest.mark.parametrize("text", CATALOGUE["texts"], ids=lambda text: text["id"])
def test_each_state_fits_in_what_laya_reads(text):
    assert isinstance(text["state"], dict)
    assert len(json.dumps(text["state"], separators=(",", ":"))) <= MAX_STATE_CHARS
