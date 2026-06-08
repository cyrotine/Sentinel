from langgraph.graph import StateGraph

from forge_workflows.state import WorkflowState


def build_graph() -> StateGraph:
    """Returns a bare StateGraph typed to WorkflowState.

    Agents are added to this graph in subsequent features.
    Each agent feature adds nodes and edges here via explicit registration.
    """
    graph: StateGraph = StateGraph(WorkflowState)
    return graph
