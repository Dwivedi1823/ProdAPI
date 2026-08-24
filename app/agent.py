




from typing import Optional
from typing_extensions import TypedDict, Annotated
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, AIMessage, BaseMessage
from langsmith import traceable

from app.config import get_settings


# === AGENT STATE ===

class AgentState(TypedDict):
    """
    State for Production agent.
    Uses Annotated with add_messages reducer for messsage accumulation.
    """
    messages: Annotated[list[BaseMessage], add_messages]
    error: Optional[str]
    retry_count: int
    model_used: str



class ProductionAgent:
    """
    Production LangGraph agent with:
    - Retry on failure (model fallback)
    - Graceful error handling
    - LangSmith tracing
    """

    def __init__(self):
        settings = get_settings()

        self.primary_llm = ChatOpenAI(
            model=settings.primary_model,
            api_key=settings.openai_api_key,
            temperature=0,
            timeout=30,
            max_retries=0 #Handling at different place
        )
        self.fallback_llm = ChatOpenAI(
            model=settings.fallback_model,
            api_key=settings.openai_api_key,
            temperature=0,
            timeout=30,
            max_retries=0
        )
        self.max_retries = settings.max_retries
        self.graph = self._build_graph()

    def _build_graph(self):
        """Build the LangGraph state machine."""

        def process_message(state: AgentState) -> dict:
            """Try to process the message with the primary model."""
            try:
                response = self.primary_llm.invoke(state["messages"])
                return {"messages": [response], "error": None, "model_used": "primary"}
            except Exception as error:
                return {
                    "error": str(error),
                    "retry_count": state["retry_count"] + 1,
                    "model_used": "",
                }

        def try_fallback(state: AgentState) -> dict:
            """Fallback to secondary model."""
            try:
                response = self.fallback_llm.invoke(state["messages"])
                return {"messages": [response], "error": None, "model_used": "fallback"}
            except Exception as error:
                return {"error": str(error), "model_used": ""}

        def handle_error(state: AgentState) -> dict:
            """Return a graceful error message."""
            return {
                "messages": [
                    AIMessage(
                        content=(
                            "I'm sorry, I'm having trouble processing your request right now. "
                            "Please try again in a moment."
                        )
                    )
                ],
                "model_used": "error_handler",
            }

        def route_after_process(state: AgentState) -> str:
            """Decide what to do after the primary model attempt."""
            if state.get("error") is None:
                return "done"
            if state["retry_count"] <= self.max_retries:
                return "fallback"
            return "error"

        def route_after_fallback(state: AgentState) -> str:
            """Decide what to do after the fallback attempt."""
            return "done" if state.get("error") is None else "error"

        graph = StateGraph(AgentState)

        graph.add_node("process", process_message)
        graph.add_node("fallback", try_fallback)
        graph.add_node("error", handle_error)

        graph.add_edge(START, "process")
        graph.add_conditional_edges(
            "process",
            route_after_process,
            {"done": END, "fallback": "fallback", "error": "error"},
        )
        graph.add_conditional_edges(
            "fallback",
            route_after_fallback,
            {"done": END, "error": "error"},
        )
        graph.add_edge("error", END)

        return graph.compile()

    @traceable(name="production_agent_invoke")
    def  invoke(self, message: str) -> dict:
        """
        Invoke the agent with a user message.
        Returns: {"reponse": str, "model_used": str,  "error": str | None}
        """
        result = self.graph.invoke({
            "messages": [HumanMessage(content=message)],
            "error": None,
            "retry_count": 0,
            "model_used": ""
        })

        return {
            "response": result["messages"][-1].content,
            "model_used": result.get("model_used", "unknown"),
            "error": result.get("error")
        }
    