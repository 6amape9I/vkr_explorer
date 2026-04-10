from __future__ import annotations

from .utils import normalize_whitespace


TOPIC_RULES: dict[str, tuple[str, ...]] = {
    "federated_learning": ("federated learning", "fedavg", "federated optimization", "federated"),
    "decentralized_learning": ("decentralized federated", "peer-to-peer", "p2p", "decentralized learning"),
    "blockchain": ("blockchain", "ethereum", "smart contract", "distributed ledger"),
    "on_chain": ("on-chain", "on chain"),
    "off_chain": ("off-chain", "off chain"),
    "zk_proof": ("zero-knowledge", "zk proof", "zkp", "zokrates"),
    "security_privacy": ("privacy", "secure", "security", "poisoning", "attack", "verifiable"),
    "incentives": ("incentive", "reputation", "reward", "penalty"),
    "survey": ("survey", "review", "systematic"),
    "distributed_training": ("distributed training", "distributed deep learning", "ddp", "fsdp"),
    "parameter_server": ("parameter server", "stale synchronous", "ps architecture"),
}

METHOD_RULES: dict[str, tuple[str, ...]] = {
    "consensus": ("consensus", "proof of", "committee"),
    "verification": ("verifiable", "verification", "proof", "zero-knowledge"),
    "aggregation": ("aggregation", "aggregator", "global model"),
    "committee_consensus": ("committee consensus",),
    "reputation": ("reputation",),
}


def infer_tags(title: str | None, abstract: str | None) -> tuple[list[str], list[str]]:
    text = normalize_whitespace(" ".join(filter(None, [title, abstract]))) or ""
    lowered = text.lower()

    topic_tags = [tag for tag, keywords in TOPIC_RULES.items() if any(keyword in lowered for keyword in keywords)]
    method_tags = [tag for tag, keywords in METHOD_RULES.items() if any(keyword in lowered for keyword in keywords)]

    return sorted(set(topic_tags)), sorted(set(method_tags))
