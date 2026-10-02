"""The reproducibility capsule (03 §7.2; eio.profile.required-capsule-fields).

The producer declares which capsule fields it recorded (bundle `provenance.capsule`); `per.projection.capsule_block`
derives `missing_fields` and `reproducible`.
"""

CAPSULE_FIELDS = ["ontology_module_hashes", "agent_manifest_hash", "policy_hash", "tool_schema_hash", "domain_profile_hash",
                  "template_ids", "binding_ids", "generator_version", "seed", "evidence_graph_schema", "evidence_source_hashes",
                  "extractor_versions", "revision", "models", "prompt_hashes", "sampling_parameters", "cache_identity",
                  "predicate_versions", "metric_view_versions", "patch", "lock_digest"]                     # schema capsule_field
