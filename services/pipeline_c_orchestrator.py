"""
services/pipeline_c_orchestrator.py — Pipeline C: Generate Lesson Feature

Graph (with Semantic Router):
START -> route_intent -> 'factual'     -> factual_search_node <-> tools
                      -> 'educational' -> self_rag_explainer -> tool_explainer <-> tools

The Semantic Router sends the state to either a fast-lane for quick factual answers
or the Self-RAG path for educational lessons.
"""

import json
import asyncio
import operator
import re
from typing import TypedDict, Annotated, AsyncGenerator, Literal

from langchain_core.messages import SystemMessage, HumanMessage, BaseMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition
from langchain_groq import ChatGroq
from langchain_community.tools import DuckDuckGoSearchRun
from langchain_ollama import ChatOllama
from pydantic import BaseModel, Field

from config import GROQ_API_KEY, DEBUGGER_MODEL, OLLAMA_BASE_URL
from services.tts import generate_tts_audio
from services.mcp_client import run_code as local_run_code
from services.self_rag import self_rag_graph

# 1. Initialize Tools
_ddg = DuckDuckGoSearchRun()

@tool
def web_search(query: str) -> str:
    """Use this tool to search the live web for current events and facts. Input should be a search query."""
    return _ddg.invoke(query)

@tool(response_format="content_and_artifact")
async def generate_and_run_code(prompt: str) -> tuple[str, dict]:
    """Generates Python code to answer the prompt and executes it in a secure sandbox.
    Use this tool if you need to calculate math, run simulations, or create data visualizations.
    Input should be a detailed prompt describing what the code should do.
    """
    print(f"[Sandbox Tool] Instructing DeepSeek to write code for: {prompt}")
    llm = ChatOllama(model=DEBUGGER_MODEL, base_url=OLLAMA_BASE_URL, temperature=0.1)
    
    sys_prompt = "You are an expert Python coder. Output ONLY valid Python code in a markdown block. Do not provide explanations or conversational text."
    response = await llm.ainvoke([SystemMessage(content=sys_prompt), HumanMessage(content=prompt)])
    
    # Extract the code block
    code = response.content
    match = re.search(r"```[a-zA-Z]*\s*\n(.*?)\n?```", response.content, re.DOTALL | re.IGNORECASE)
    if match:
        code = match.group(1).strip()
        
    print(f"[Sandbox Tool] Running code in Sandbox...\n{code[:100]}...")
    output, has_error, stderr, images = await local_run_code(code, language="python")
    
    # Format the result for the Explainer model
    if has_error:
        content = f"Execution failed with error:\n{output}\nPlease analyze this error."
    else:
        content = f"Code executed successfully.\nOutput:\n{output}"
        
    # The artifact will be stored in the LangGraph state
    artifact = {"code": code, "output": output, "has_error": has_error, "images": images}
    return content, artifact

tools = [web_search, generate_and_run_code]

# 2. Initialize Models
if GROQ_API_KEY:
    llm_router = ChatGroq(model="llama-3.1-8b-instant", api_key=GROQ_API_KEY)
    llm_explainer = ChatGroq(model="llama-3.3-70b-versatile", api_key=GROQ_API_KEY, streaming=True)
    # Bind the tool specifically to the Explainer
    llm_explainer_with_tools = llm_explainer.bind_tools(tools)
    # Keep bare LLM as fallback when Groq's tool calling fails
    llm_explainer_bare = llm_explainer
else:
    llm_router = None
    llm_explainer_with_tools = None
    llm_explainer_bare = None

# 3. Define State
class AgentStateC(TypedDict):
    topic: str
    self_rag_lesson: str  # Grounded lesson from Self-RAG sub-graph
    messages: Annotated[list[BaseMessage], add_messages]
    sandbox_artifacts: Annotated[list[dict], operator.add]

class RouteIntent(BaseModel):
    intent: Literal["factual", "educational"] = Field(
        description="Classify the user intent. 'factual' for real-time data, current events, or simple facts. 'educational' for learning a concept, understanding a topic, or reviewing a document."
    )

# 4. Define Nodes
async def route_intent_node(state: AgentStateC, config: RunnableConfig) -> Literal["factual", "educational"]:
    """Semantic Router to classify the user intent."""
    if not llm_router:
        return "educational" # Fallback
    
    topic = state["topic"]
    router_prompt = SystemMessage(
        content="You are an intent classifier. Categorize the user query into exactly one of two categories: 'factual' or 'educational'.\n"
        "'factual': The user is asking for real-time data, current events, or simple facts (e.g., 'Who won yesterday's match?', 'What is the weather?').\n"
        "'educational': The user is asking to learn a concept, understand a topic, or review a document (e.g., 'Explain binary trees', 'Summarize my uploaded PDF').\n"
        "Output EXACTLY and ONLY the word 'factual' or 'educational'. Do not include any punctuation or extra text."
    )
    
    try:
        response = await llm_router.ainvoke([router_prompt, HumanMessage(content=topic)], config)
        intent = response.content.strip().lower()
        if "factual" in intent:
            return "factual"
        return "educational"
    except Exception as e:
        print(f"[Router Error] Defaulting to educational. Error: {e}")
        return "educational"


async def _invoke_with_fallback(llm_with_tools, llm_bare, messages, config):
    """Try tool-bound LLM first; on Groq tool_use_failed, retry with bare LLM."""
    try:
        return await llm_with_tools.ainvoke(messages, config)
    except Exception as e:
        error_str = str(e)
        if "tool_use_failed" in error_str or "Failed to call a function" in error_str:
            print(f"[Pipeline C] Groq tool_use_failed — retrying without tools. Error: {error_str[:200]}")
            return await llm_bare.ainvoke(messages, config)
        raise  # Re-raise if it's a different error


async def factual_search_node(state: AgentStateC, config: RunnableConfig):
    """Path A: Handles factual queries quickly using tools."""
    if not llm_explainer_with_tools:
        raise RuntimeError("GROQ_API_KEY is not set.")
    
    messages = state["messages"]
    topic = state["topic"]
    
    sys_msg = SystemMessage(
        content=(
            "You are a direct and concise assistant answering a factual question.\n"
            "If you do not know the answer, YOU MUST use the 'web_search' tool to find the actual, literal answer.\n"
            "Output a direct, concise answer. DO NOT act like a teacher and DO NOT generate a full lesson layout. Just answer the question.\n"
            "You can use 'generate_and_run_code' if you need to calculate math or parse data, but only if required."
        )
    )
    
    if not messages:
        first_msg = HumanMessage(content=topic)
        invoke_messages = [sys_msg, first_msg]
        response = await _invoke_with_fallback(llm_explainer_with_tools, llm_explainer_bare, invoke_messages, config)
        return {"messages": [first_msg, response]}
    else:
        invoke_messages = [sys_msg] + messages
        response = await _invoke_with_fallback(llm_explainer_with_tools, llm_explainer_bare, invoke_messages, config)
        return {"messages": [response]}


async def self_rag_explainer_node(state: AgentStateC, config: RunnableConfig):
    """Path B (Step 1): Runs the Self-RAG sub-graph to produce a grounded lesson."""
    topic = state["topic"]
    
    print(f"[Pipeline C | Self-RAG] Starting Self-RAG for: {topic}")
    
    # Run the Self-RAG sub-graph
    rag_result = await asyncio.to_thread(
        self_rag_graph.invoke,
        {
            "question": topic,
            "documents": [],
            "generation": "",
            "loop_count": 0,
            "web_search_needed": False,
        }
    )
    
    grounded_lesson = rag_result.get("generation", "")
    print(f"[Pipeline C | Self-RAG] Got grounded lesson ({len(grounded_lesson)} chars)")
    
    return {"self_rag_lesson": grounded_lesson}


async def tool_explainer_node(state: AgentStateC, config: RunnableConfig):
    """Path B (Step 2): Enhances the grounded lesson with tools if needed."""
    if not llm_explainer_with_tools:
        raise RuntimeError("GROQ_API_KEY is not set.")
    
    messages = state["messages"]
    grounded_lesson = state.get("self_rag_lesson", "")
    
    sys_msg = SystemMessage(
        content=(
            "You are an AI Teacher. You have been provided with a grounded, fact-checked lesson "
            "produced by a Self-RAG pipeline. Your job is to enhance this lesson with:\n"
            "1. Use 'generate_and_run_code' to write Python code if the topic involves programming, "
            "math, or data visualization. ONLY call the sandbox if required to demonstrate a concept.\n"
            "2. Use 'web_search' ONLY if you need very recent/current information not in the lesson.\n\n"
            "CRITICAL SANDBOX RULES: When writing Python code to be executed in the sandbox, you are strictly limited to the standard Python library and the following pre-installed packages: numpy, pandas, matplotlib, math, random, json, and datetime. Do not attempt to import any other third-party libraries.\n\n"
            "IMPORTANT: Output the FULL enhanced lesson in Markdown. Do NOT remove content from "
            "the grounded lesson — only ADD to it.\n\n"
            f"Topic: {state['topic']}\n"
            f"--- Grounded Lesson from Self-RAG ---\n{grounded_lesson}\n"
            f"--- End of Grounded Lesson ---\n\n"
            "Enhance this lesson with code examples and visualizations where appropriate."
        )
    )
    
    if not messages:
        first_msg = HumanMessage(content=f"Please enhance the lesson on: {state['topic']}.")
        invoke_messages = [sys_msg, first_msg]
        response = await _invoke_with_fallback(llm_explainer_with_tools, llm_explainer_bare, invoke_messages, config)
        return {"messages": [first_msg, response]}
    else:
        invoke_messages = [sys_msg] + messages
        response = await _invoke_with_fallback(llm_explainer_with_tools, llm_explainer_bare, invoke_messages, config)
        return {"messages": [response]}


async def custom_tool_node(state: AgentStateC, config: RunnableConfig):
    """Wrapper around ToolNode to extract artifacts and push them to state."""
    node = ToolNode(tools)
    result = await node.ainvoke(state, config)
    
    new_artifacts = []
    if "messages" in result:
        for msg in result["messages"]:
            if hasattr(msg, "artifact") and msg.artifact:
                new_artifacts.append(msg.artifact)
                
    if new_artifacts:
        return {"messages": result["messages"], "sandbox_artifacts": new_artifacts}
    return result

# 5. Compile LangGraph
workflow_c = StateGraph(AgentStateC)

workflow_c.add_node("factual_search", factual_search_node)
workflow_c.add_node("self_rag_explainer", self_rag_explainer_node)
workflow_c.add_node("tool_explainer", tool_explainer_node)
workflow_c.add_node("tools", custom_tool_node)

# Add conditional edges from START
workflow_c.add_conditional_edges(
    START,
    route_intent_node,
    {
        "factual": "factual_search",
        "educational": "self_rag_explainer"
    }
)

workflow_c.add_edge("self_rag_explainer", "tool_explainer")

# Routing: if a node calls a tool -> tools, else -> END
workflow_c.add_conditional_edges("factual_search", tools_condition, {"tools": "tools", END: END})
workflow_c.add_conditional_edges("tool_explainer", tools_condition, {"tools": "tools", END: END})

# After tools run, we need to return to the node that called them.
def route_after_tools(state: AgentStateC) -> str:
    """Route back to the correct node after tools finish."""
    # We can check the messages. If there is a 'self_rag_lesson', it's the educational path.
    if state.get("self_rag_lesson"):
        return "tool_explainer"
    return "factual_search"

workflow_c.add_conditional_edges(
    "tools",
    route_after_tools,
    {
        "factual_search": "factual_search",
        "tool_explainer": "tool_explainer"
    }
)

graph_c = workflow_c.compile()


# 6. Streaming function
async def stream_pipeline_c(topic: str) -> AsyncGenerator[str, None]:
    if not GROQ_API_KEY:
        yield f"data: {json.dumps({'type': 'error', 'content': 'GROQ API key not configured.'})}\n\n"
        yield f"data: {json.dumps({'type': 'text_complete'})}\n\n"
        return

    yield f"data: {json.dumps({'type': 'log', 'message': 'Classifying intent...'})}\n\n"

    full_text = ""
    has_started_explainer = False
    has_started_self_rag = False
    has_started_factual = False

    try:
        initial_state = {"topic": topic, "self_rag_lesson": "", "messages": [], "sandbox_artifacts": []}
        
        # We use astream_events to get real-time tokens from the LLM and tool statuses
        async for event in graph_c.astream_events(initial_state, version="v2"):
            kind = event["event"]
            node_name = event["metadata"].get("langgraph_node")
            
            # Log Self-RAG progress
            if kind == "on_chain_start" and node_name == "self_rag_explainer":
                if not has_started_self_rag:
                    yield f"data: {json.dumps({'type': 'log', 'message': '🔍 Self-RAG: Retrieving & grading documents...'})}\n\n"
                    has_started_self_rag = True

            if kind == "on_chat_model_start" and node_name == "tool_explainer":
                if not has_started_explainer:
                    yield f"data: {json.dumps({'type': 'log', 'message': '✍️ Generating enhanced lesson...'})}\n\n"
                    has_started_explainer = True
                    
            if kind == "on_chat_model_start" and node_name == "factual_search":
                if not has_started_factual:
                    yield f"data: {json.dumps({'type': 'log', 'message': '🔍 Factual search: Formulating answer...'})}\n\n"
                    has_started_factual = True

            # Stream LLM tokens from tool_explainer AND factual_search
            elif kind == "on_chat_model_stream" and node_name in ["tool_explainer", "factual_search"]:
                chunk_msg = event["data"]["chunk"]
                if chunk_msg.content:
                    if isinstance(chunk_msg.content, str):
                        content = chunk_msg.content
                        full_text += content
                        yield f"data: {json.dumps({'type': 'chunk', 'content': content})}\n\n"
                    elif isinstance(chunk_msg.content, list):
                        for item in chunk_msg.content:
                            if isinstance(item, dict) and item.get("type") == "text":
                                content = item.get("text", "")
                                full_text += content
                                yield f"data: {json.dumps({'type': 'chunk', 'content': content})}\n\n"

            # Log Tool executions
            elif kind == "on_tool_start":
                tool_name = event["name"]
                if tool_name == "generate_and_run_code":
                    yield f"data: {json.dumps({'type': 'log', 'message': 'Invoking DeepSeek to write code...'})}\n\n"
                else:
                    yield f"data: {json.dumps({'type': 'log', 'message': f'Searching web with {tool_name}...'})}\n\n"
                    
            elif kind == "on_tool_end":
                tool_msg = event["data"].get("output")
                if hasattr(tool_msg, "artifact") and tool_msg.artifact:
                    # Stream the sandbox artifact to the frontend for the split-screen UI
                    yield f"data: {json.dumps({'type': 'sandbox_artifact', 'artifact': tool_msg.artifact})}\n\n"
                    
    except Exception as exc:
        import traceback
        traceback.print_exc()
        yield f"data: {json.dumps({'type': 'error', 'content': str(exc)})}\n\n"
        yield f"data: {json.dumps({'type': 'text_complete'})}\n\n"
        return

    # Signal text_complete so the frontend unlocks the UI
    yield f"data: {json.dumps({'type': 'text_complete'})}\n\n"

    # Generate TTS for the lesson
    if full_text.strip():
        yield f"data: {json.dumps({'type': 'log', 'message': 'Generating audio...'})}\n\n"
        audio_base64 = None
        try:
            audio_base64 = await asyncio.to_thread(generate_tts_audio, full_text)
        except Exception as e:
            print(f"[Pipeline C] TTS error: {e}")

        if audio_base64:
            yield f"data: {json.dumps({'type': 'audio', 'audio_base64': audio_base64})}\n\n"
