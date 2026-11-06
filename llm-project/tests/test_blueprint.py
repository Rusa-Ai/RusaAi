import unittest

from model.blueprint import ModelSpec, MoESpec, ProjectBlueprint


class ModelSpecValidationTests(unittest.TestCase):
    def test_default_blueprint_is_valid_and_not_claimed_trained(self):
        blueprint = ProjectBlueprint()
        blueprint.validate()
        self.assertEqual(blueprint.status, "PLANNED")
        self.assertEqual(blueprint.model.name, "rusa-ai-base-blueprint")

    def test_hidden_size_must_divide_evenly_into_attention_heads(self):
        with self.assertRaisesRegex(ValueError, "hidden_size"):
            ModelSpec(hidden_size=1000, attention_heads=96).validate()

    def test_attention_heads_must_be_divisible_by_kv_heads(self):
        with self.assertRaisesRegex(ValueError, "kv_heads"):
            ModelSpec(attention_heads=12, kv_heads=5).validate()

    def test_attention_dimensions_must_be_positive(self):
        with self.assertRaisesRegex(ValueError, "attention_heads"):
            ModelSpec(attention_heads=0).validate()
        with self.assertRaisesRegex(ValueError, "kv_heads"):
            ModelSpec(kv_heads=0).validate()

    def test_moe_top_k_cannot_exceed_expert_count(self):
        with self.assertRaisesRegex(ValueError, "experts_per_token"):
            ModelSpec(moe=MoESpec(num_experts=4, experts_per_token=5)).validate()

    def test_moe_counts_must_be_positive(self):
        with self.assertRaisesRegex(ValueError, "num_experts"):
            ModelSpec(moe=MoESpec(num_experts=0)).validate()
        with self.assertRaisesRegex(ValueError, "experts_per_token"):
            ModelSpec(moe=MoESpec(experts_per_token=0)).validate()

    def test_modalities_must_be_non_empty_and_unique(self):
        with self.assertRaisesRegex(ValueError, "modalities"):
            ModelSpec(modalities=[]).validate()
        with self.assertRaisesRegex(ValueError, "duplicates"):
            ModelSpec(modalities=["text", "text"]).validate()

    def test_name_must_not_be_blank(self):
        with self.assertRaisesRegex(ValueError, "name"):
            ModelSpec(name="   ").validate()


if __name__ == "__main__":
    unittest.main()
