from agents.o2c_agent.agent import root_agent


def test_root_agent_has_creator_and_reviewer():
    names = {a.name for a in root_agent.sub_agents}
    assert names == {"creator", "reviewer"}


def test_root_agent_model_is_configured():
    assert root_agent.model  # non-empty string
