"""Interface and numerical compatibility checks without loading a large checkpoint."""
from types import SimpleNamespace

import pytest
import torch
from torch import nn

from jev_core.nanojev import LocalNanoJev, decision_model


class TinyBody(nn.Module):
    def __init__(self):
        super().__init__()
        self.config = SimpleNamespace(hidden_size=8)
        self.embedding = nn.Embedding(50, 8)
    def forward(self, input_ids, attention_mask, use_cache):
        return SimpleNamespace(last_hidden_state=self.embedding(input_ids))


def test_decision_head_matches_reference_formula_for_variable_length_candidates():
    torch.manual_seed(7)
    model = decision_model(TinyBody(), "attention").eval()
    paths = [[1, 2, 3], [4, 5], [6]]
    with torch.inference_mode():
        actual = model(paths, 0)
        # Upstream one-choice-set formula: gather EOS, norm, scalar + set residual.
        h = model.norm(model.backbone.embedding(torch.tensor([[3, 5, 6]])))
        u = model.set_project(torch.cat((h, torch.full((1, 3, 1), torch.tensor(3.).log())), dim=-1))
        mixed, _ = model.set_attention(u, u, u, key_padding_mask=torch.zeros((1,3), dtype=torch.bool), need_weights=False)
        expected = (model.scalar(h) + model.set_output(torch.tanh(u + mixed))).squeeze()
    torch.testing.assert_close(actual, expected, rtol=1e-5, atol=1e-6)


class RecordingTokenizer:
    eos_token_id = 3
    pad_token_id = 0
    def __init__(self):
        self.inputs = []
    def encode(self, text, add_special_tokens=False):
        self.inputs.append(text)
        return [1] * len(text)


class NoneChooser:
    def __init__(self):
        self.path_counts = []
    def __call__(self, paths, pad):
        self.path_counts.append(len(paths))
        return torch.tensor([0.] * (len(paths)-1) + [10.])


def configured_model():
    model = LocalNanoJev()
    model.device, model.precision, model.max_tokens = "cpu", "fp32", 8192
    model.tokenizer = RecordingTokenizer()
    model.model = NoneChooser()
    model.batch_size = 4
    return model


def test_every_candidate_is_processed_and_last_singleton_still_gets_none():
    model = configured_model()
    question = "Very long question " * 60 + "TAIL_MUST_SURVIVE"
    candidates = [{"document_name":"file", "section":"section", "text":f"passage {i}"} for i in range(9)]
    result = model.rank(question, candidates)
    assert len(result) == 9
    assert model.model.path_counts == [5, 5, 2]
    assert all(row["jev"]["choice"] == "none" for row in result)
    assert not any(row["jev"]["supports_over_none"] for row in result)
    assert any("TAIL_MUST_SURVIVE" in text for text in model.tokenizer.inputs)


def test_context_overflow_is_explicit_instead_of_silent_truncation():
    model = configured_model()
    model.max_tokens = 20
    with pytest.raises(RuntimeError, match="超出本地模型上下文"):
        model.rank("question", [{"document_name":"file","section":"s","text":"evidence"}])
    assert not model.model.path_counts
