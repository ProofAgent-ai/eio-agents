"""Context artifacts of a record (03 §13.1)."""


def embedded(artifacts):
    """The context artifacts whose text is in the archive: the only ones searched or cited."""
    return [a for a in artifacts if a.get("embedded", True)]
