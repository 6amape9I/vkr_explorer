from vkr_article_dataset.tagger import infer_tags


def test_infer_tags_for_blockchain_fl() -> None:
    title = "Advancing Blockchain-based Federated Learning through Verifiable Off-chain Computations"
    abstract = "We explore verifiable off-chain computations using zero-knowledge proofs for blockchain-based federated learning."
    topic_tags, method_tags = infer_tags(title=title, abstract=abstract)

    assert "federated_learning" in topic_tags
    assert "blockchain" in topic_tags
    assert "off_chain" in topic_tags
    assert "zk_proof" in topic_tags
    assert "verification" in method_tags
