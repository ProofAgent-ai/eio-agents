"""Source-complete, synthetic native input for the rc4 full-score gate.

Every number must be recomputed from the bundle and EIO ontology.  The
fixture contains no producer-supplied score, freshness assertion or receipt.
"""

from eio_agents import __version__
from eio_agents.base.canon import H
from eio_agents.ontology import load
from eio_agents.per import bundle as native_bundle
from eio_agents.semantics import ids
from test_native_reportability import with_citation


PRIVATE_MARKER = "zqxjvw-full-score-private-marker"
CONTEXT_TEXT = "Synthetic public system instructions: answer helpfully and cite evidence."


def reissued_cited_bundle():
    """Current-release synthetic citation vector without optional score inputs."""
    bundle, _, _ = with_citation()
    ontology = load()
    # Reissue the synthetic 0.5 source as a current-release test vector. Its
    # archived original remains unchanged and must still fail a 0.6 pin check.
    bundle["header"]["eio_agents"].update(
        version=__version__, ontology_sha256=ontology.ontology_sha256)
    bundle["header"]["eio"].update(
        release=ontology.release, ontology_digest=ontology.ontology_digest,
        ontology_sha256=ontology.ontology_sha256)
    remap = {}
    for claim in bundle["claims"]:
        old_id = claim["id"]
        predicate = claim["predicate"]
        module, version = ontology.mod_of_pred[predicate]
        claim["predicate_version"] = ontology.pred[predicate]["version"]
        claim["provenance"].update(
            module=module, module_version=version,
            module_hash=ontology.modules[module])
        claim["id"] = ids.claim_id(
            claim["run_id"], predicate, claim["predicate_version"],
            claim["parameters"].get("legacy_check"), claim["turn_indices"])
        remap[old_id] = claim["id"]
    for binding in bundle["native_scoring"]["claim_bindings"]:
        binding["claim_id"] = remap[binding["claim_id"]]
    for citation in bundle["native_scoring"]["proof_citations"]:
        citation["claim_id"] = remap[citation["claim_id"]]
    bundle["ballots"]["pooled_claims"] = [remap[cid] for cid in bundle["ballots"]["pooled_claims"]]
    for ballot in bundle["ballots"]["ballots"]:
        ballot["claim_id"] = remap[ballot["claim_id"]]
    reseal_stages(bundle)
    return bundle


def source_complete_bundle():
    bundle = reissued_cited_bundle()
    ontology = load()
    frameworks = ("eio.framework.owasp-agentic-threats", "eio.framework.aiuc-1")
    predicates = {claim["predicate"] for claim in bundle["claims"]}
    controls = [
        (framework, control_id)
        for framework in frameworks
        for control_id in ontology.frameworks[framework]["controls"]
        if predicates.intersection(ontology.controls[control_id]["predicate_targets"])
    ]
    assert len(controls) == 6
    bundle["scope"]["frameworks"]["candidates"] = [
        {"id": framework, "basis": "synthetic scope"} for framework in frameworks
    ]
    bundle["native_scoring"]["applicable_controls"] = [
        {"framework": framework, "control_id": control_id}
        for framework, control_id in controls
    ]
    digest = H(CONTEXT_TEXT.encode("utf-8"))
    artifact = {"artifact_kind": "eio.artifact.system-prompt", "name": "synthetic-public.md",
                "sha256": digest, "code_points": len(CONTEXT_TEXT), "embedded": True,
                "data_class": "eio.data.public"}
    bundle["sources"]["context_artifacts"] = [artifact]
    bundle["sources"]["context_texts"] = {artifact["name"]: CONTEXT_TEXT}
    bundle["provenance"]["record"]["inputs"]["context_artifacts"] = [artifact]
    bundle["native_scoring"]["context_ratings"] = [
        {"criterion_id": criterion, "artifact_name": artifact["name"],
         "artifact_sha256": digest, "assessor_id": "synthetic-assessor", "rating": 80}
        for criterion in ("eio.context.role-clarity", "eio.context.grounding-sufficiency")
    ]
    reseal_stages(bundle)
    return bundle


def replace_context_text(bundle, text):
    """Alter captured context while preserving a valid, source-bound digest."""
    digest = H(text.encode("utf-8"))
    bundle["sources"]["context_texts"]["synthetic-public.md"] = text
    for artifact in (bundle["sources"]["context_artifacts"][0],
                     bundle["provenance"]["record"]["inputs"]["context_artifacts"][0]):
        artifact["sha256"] = digest
        artifact["code_points"] = len(text)
    for rating in bundle["native_scoring"]["context_ratings"]:
        rating["artifact_sha256"] = digest
    return reseal_stages(bundle)


def reseal_stages(bundle):
    """Restamp a changed source so a negative vector reaches semantic checks."""
    for stage in bundle["stage_records"]:
        stage["output_sha256"] = native_bundle.stage_digest(bundle, stage["sections"])
    return bundle
