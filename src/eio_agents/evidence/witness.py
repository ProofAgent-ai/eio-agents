"""The witness rule (01 §6.3 W4; eio.profile.witness-rule; PER-68): `can_prove` and `witnessing_anchored`, as free functions
over a loaded release `eio`. The rule is defined once, by the release (`eio_agents.ontology.Ontology`)."""


def can_prove(eio, kind, source_type, paired_call=False):
    """Whether a ref of this kind and source type can prove agent behaviour under the loaded release `eio`."""
    return eio.can_prove(kind, source_type, paired_call)


def witnessing_anchored(eio, ref):
    """A ref that can prove agent behaviour and carries a witnessing anchor of the release."""
    return eio.witnessing_anchored(ref)
