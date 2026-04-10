from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TagRule:
    patterns: tuple[str, ...]
    threshold: int


TOPIC_RULES: dict[str, TagRule] = {
    "federated_learning": TagRule(
        patterns=("federated learning", "fedavg", "federated optimization", "federated"),
        threshold=3,
    ),
    "decentralized_learning": TagRule(
        patterns=("decentralized federated", "peer-to-peer", "p2p", "decentralized learning"),
        threshold=3,
    ),
    "blockchain": TagRule(
        patterns=("blockchain", "ethereum", "smart contract", "distributed ledger"),
        threshold=3,
    ),
    "on_chain": TagRule(
        patterns=("on-chain", "on chain"),
        threshold=3,
    ),
    "off_chain": TagRule(
        patterns=("off-chain", "off chain"),
        threshold=3,
    ),
    "zk_proof": TagRule(
        patterns=("zero-knowledge", "zk proof", "zkp", "zokrates"),
        threshold=3,
    ),
    "security_privacy": TagRule(
        patterns=("privacy", "secure", "security", "poisoning", "attack", "verifiable"),
        threshold=3,
    ),
    "incentives": TagRule(
        patterns=("incentive", "reputation", "reward", "penalty"),
        threshold=3,
    ),
    "survey": TagRule(
        patterns=("survey", "review", "systematic"),
        threshold=3,
    ),
    "distributed_training": TagRule(
        patterns=("distributed training", "distributed deep learning", "ddp", "fsdp"),
        threshold=4,
    ),
    "parameter_server": TagRule(
        patterns=("parameter server", "stale synchronous", "ps architecture"),
        threshold=4,
    ),
}


METHOD_RULES: dict[str, TagRule] = {
    "consensus": TagRule(
        patterns=("consensus", "proof of", "committee"),
        threshold=3,
    ),
    "verification": TagRule(
        patterns=("verifiable", "verification", "proof", "zero-knowledge"),
        threshold=3,
    ),
    "aggregation": TagRule(
        patterns=("aggregation", "aggregator", "global model"),
        threshold=3,
    ),
    "committee_consensus": TagRule(
        patterns=("committee consensus",),
        threshold=3,
    ),
    "reputation": TagRule(
        patterns=("reputation",),
        threshold=3,
    ),
}
