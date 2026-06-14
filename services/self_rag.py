"""
services/self_rag.py — Self-Reflective RAG Sub-Graph for Pipeline C

Implements a strict Self-RAG state machine that:
1. Routes the question (index vs web search)
2. Retrieves documents from Pinecone (or falls back to DuckDuckGo)
3. Grades documents for relevance
4. Generates an answer grounded ONLY in those documents
5. Checks for hallucinations and answer quality
6. Loops back to rewrite/regenerate if quality checks fail

Graph:
  START → route_question → [retrieve | web_search] → grade_documents
       → [generate | rewrite_question → retrieve]
       → check_hallucinations_and_answer
       → [generate (retry) | rewrite_question | END]
"""

from __future__ import annotations

import os
from typing import TypedDict

from langchain_core.prompts import ChatPromptTemplate
from langchain_groq import ChatGroq
from langchain_community.tools import DuckDuckGoSearchRun
from langgraph.graph import StateGraph, START, END
from pydantic import BaseModel, Field

from config import GROQ_API_KEY, PINECONE_API_KEY, PINECONE_INDEX_NAME, OLLAMA_BASE_URL

# ---------------------------------------------------------------------------
# 1. Graph State
# ---------------------------------------------------------------------------

class SelfRagState(TypedDict):
    """State for the Self-RAG sub-graph."""
    question: str          # The user's query or the topic Agent 1 assigned
    documents: list[str]   # Context pulled from vector DB / web
    generation: str        # The drafted explanation from the LLM
    loop_count: int        # Prevents infinite loops (max 3)
    web_search_needed: bool  # Flag set by grade_documents when all docs irrelevant


# ---------------------------------------------------------------------------
# 2. Pydantic Grader Schemas
# ---------------------------------------------------------------------------

class GradeDocument(BaseModel):
    """Binary score for document relevance to the question."""
    binary_score: str = Field(
        description="Is the document relevant to the question? 'yes' or 'no'"
    )

class GradeHallucination(BaseModel):
    """Binary score for whether the generation is grounded in documents."""
    binary_score: str = Field(
        description="Is the generation grounded in the provided documents? 'yes' = grounded, 'no' = hallucinated"
    )

class GradeAnswer(BaseModel):
    """Binary score for whether the generation resolves the question."""
    binary_score: str = Field(
        description="Does the generation answer the question? 'yes' or 'no'"
    )


# ---------------------------------------------------------------------------
# 3. Initialize LLMs + Graders
# ---------------------------------------------------------------------------

_grader_llm = None
_generator_llm = None
_doc_grader = None
_hallucination_grader = None
_answer_grader = None
_retriever = None
_ddg_search = None

def _init_components():
    """Lazy initialization of LLMs, graders, and retriever."""
    global _grader_llm, _generator_llm
    global _doc_grader, _hallucination_grader, _answer_grader
    global _retriever, _ddg_search

    if _grader_llm is not None:
        return  # Already initialized

    if not GROQ_API_KEY:
        raise RuntimeError("GROQ_API_KEY is required for Self-RAG graders.")

    # --- LLMs ---
    _grader_llm = ChatGroq(model="llama-3.3-70b-versatile", api_key=GROQ_API_KEY, temperature=0)
    _generator_llm = ChatGroq(model="llama-3.3-70b-versatile", api_key=GROQ_API_KEY, temperature=0.3)

    # --- Document Grader ---
    doc_grader_prompt = ChatPromptTemplate.from_messages([
        ("system",
         "You are a grader assessing the relevance of a retrieved document to a user question. "
         "If the document contains keyword(s) or semantic meaning related to the question, grade it as relevant. "
         "Give a binary 'yes' or 'no' score."),
        ("human", "Retrieved document:\n\n{document}\n\nUser question: {question}"),
    ])
    _doc_grader = doc_grader_prompt | _grader_llm.with_structured_output(GradeDocument)

    # --- Hallucination Grader ---
    hallucination_prompt = ChatPromptTemplate.from_messages([
        ("system",
         "You are a grader assessing whether an LLM generation is grounded in / supported by "
         "a set of retrieved facts. Give a binary 'yes' or 'no' score. "
         "'yes' means the generation is grounded in the facts (no hallucination). "
         "'no' means the generation contains information NOT supported by the facts."),
        ("human", "Set of facts:\n\n{documents}\n\nLLM generation: {generation}"),
    ])
    _hallucination_grader = hallucination_prompt | _grader_llm.with_structured_output(GradeHallucination)

    # --- Answer Grader ---
    answer_prompt = ChatPromptTemplate.from_messages([
        ("system",
         "You are a grader assessing whether an answer addresses / resolves a question. "
         "Give a binary 'yes' or 'no' score. 'yes' means the answer resolves the question."),
        ("human", "User question:\n\n{question}\n\nLLM generation: {generation}"),
    ])
    _answer_grader = answer_prompt | _grader_llm.with_structured_output(GradeAnswer)

    # --- DuckDuckGo fallback ---
    _ddg_search = DuckDuckGoSearchRun()

    # --- Pinecone Retriever ---
    if PINECONE_API_KEY:
        try:
            from pinecone import Pinecone
            from langchain_pinecone import PineconeVectorStore
            from langchain_ollama import OllamaEmbeddings

            embeddings = OllamaEmbeddings(
                model="nomic-embed-text",
                base_url=OLLAMA_BASE_URL,
            )
            pc = Pinecone(api_key=PINECONE_API_KEY)

            # Check if the index exists, create if not
            existing_indexes = [idx.name for idx in pc.list_indexes()]
            if PINECONE_INDEX_NAME not in existing_indexes:
                from pinecone import ServerlessSpec
                pc.create_index(
                    name=PINECONE_INDEX_NAME,
                    dimension=768,  # nomic-embed-text dimension
                    metric="cosine",
                    spec=ServerlessSpec(cloud="aws", region="us-east-1"),
                )
                print(f"[Self-RAG] Created Pinecone index: {PINECONE_INDEX_NAME}")

            _retriever = PineconeVectorStore(
                index=pc.Index(PINECONE_INDEX_NAME),
                embedding=embeddings,
            ).as_retriever(search_kwargs={"k": 4})
            print(f"[Self-RAG] Pinecone retriever initialized on index: {PINECONE_INDEX_NAME}")
        except Exception as e:
            print(f"[Self-RAG] WARNING: Pinecone init failed ({e}). Falling back to web search.")
            _retriever = None
    else:
        print("[Self-RAG] No Pinecone API key. Using web search for retrieval.")


# ---------------------------------------------------------------------------
# 4. Node Functions
# ---------------------------------------------------------------------------

def route_question(state: SelfRagState) -> dict:
    """
    Route the question: if we have a Pinecone index, go to retrieve.
    Otherwise, flag for web search.
    """
    _init_components()
    print(f"[Self-RAG | Route] Routing question: {state['question'][:80]}...")

    if _retriever is not None:
        # We have a vector index — try retrieval first
        return {"web_search_needed": False}
    else:
        # No index — go directly to web search
        return {"web_search_needed": True}


def retrieve(state: SelfRagState) -> dict:
    """
    Retrieves documents from Pinecone vector store.
    """
    _init_components()
    question = state["question"]
    print(f"[Self-RAG | Retrieve] Querying Pinecone for: {question[:80]}...")

    if _retriever is None:
        print("[Self-RAG | Retrieve] No retriever available, returning empty.")
        return {"documents": []}

    try:
        docs = _retriever.invoke(question)
        doc_texts = [doc.page_content for doc in docs]
        print(f"[Self-RAG | Retrieve] Got {len(doc_texts)} documents from Pinecone.")
        return {"documents": doc_texts}
    except Exception as e:
        print(f"[Self-RAG | Retrieve] Pinecone query failed: {e}")
        return {"documents": []}


def web_search_node(state: SelfRagState) -> dict:
    """
    Fallback: uses DuckDuckGo web search when docs are irrelevant or no index.
    """
    _init_components()
    question = state["question"]
    print(f"[Self-RAG | Web Search] Searching web for: {question[:80]}...")

    try:
        results = _ddg_search.invoke(question)
        # Split the web search results into document chunks
        doc_texts = [chunk.strip() for chunk in results.split("\n") if chunk.strip()]
        if not doc_texts:
            doc_texts = [results]
        print(f"[Self-RAG | Web Search] Got {len(doc_texts)} chunks from web.")
        return {"documents": doc_texts}
    except Exception as e:
        print(f"[Self-RAG | Web Search] Failed: {e}")
        return {"documents": [f"Web search failed: {e}"]}


def grade_documents(state: SelfRagState) -> dict:
    """
    Iterates through retrieved documents using the DocumentGrader.
    Filters out irrelevant docs. Sets web_search_needed if all are irrelevant.
    """
    _init_components()
    question = state["question"]
    documents = state.get("documents", [])
    print(f"[Self-RAG | Grade] Grading {len(documents)} documents...")

    if not documents:
        print("[Self-RAG | Grade] No documents to grade. Flagging for web search.")
        return {"documents": [], "web_search_needed": True}

    relevant_docs = []
    for i, doc in enumerate(documents):
        try:
            score = _doc_grader.invoke({"question": question, "document": doc})
            if score.binary_score.lower() == "yes":
                relevant_docs.append(doc)
                print(f"  [Doc {i+1}] ✅ Relevant")
            else:
                print(f"  [Doc {i+1}] ❌ Irrelevant")
        except Exception as e:
            print(f"  [Doc {i+1}] ⚠️ Grading error: {e}, keeping doc.")
            relevant_docs.append(doc)

    if not relevant_docs:
        print("[Self-RAG | Grade] All documents irrelevant. Flagging for web search.")
        return {"documents": [], "web_search_needed": True}

    print(f"[Self-RAG | Grade] {len(relevant_docs)}/{len(documents)} documents passed.")
    return {"documents": relevant_docs, "web_search_needed": False}


def generate(state: SelfRagState) -> dict:
    """
    Generates a lesson/explanation using ONLY the filtered documents.
    Increments loop_count.
    """
    _init_components()
    question = state["question"]
    documents = state.get("documents", [])
    loop_count = state.get("loop_count", 0)

    print(f"[Self-RAG | Generate] Drafting answer (attempt {loop_count + 1})...")

    docs_context = "\n\n---\n\n".join(documents) if documents else "No documents available."

    prompt = ChatPromptTemplate.from_messages([
        ("system",
         "You are an expert AI teacher. Generate a comprehensive, well-structured "
         "lesson in Markdown format. You MUST ground your answer ONLY in the provided "
         "context documents. Do not make up facts. Use clear headings, bullet points, "
         "and code examples where appropriate."),
        ("human",
         "Question/Topic: {question}\n\n"
         "Context Documents:\n{documents}\n\n"
         "Generate the lesson:"),
    ])

    chain = prompt | _generator_llm
    response = chain.invoke({"question": question, "documents": docs_context})

    print(f"[Self-RAG | Generate] Generated {len(response.content)} chars.")
    return {"generation": response.content, "loop_count": loop_count + 1}


def rewrite_question(state: SelfRagState) -> dict:
    """
    Uses the LLM to rewrite the question for better retrieval.
    """
    _init_components()
    question = state["question"]
    print(f"[Self-RAG | Rewrite] Rewriting question: {question[:80]}...")

    prompt = ChatPromptTemplate.from_messages([
        ("system",
         "You are a question rewriter. Your goal is to rewrite the given question "
         "to produce a better version that is optimized for vectorstore retrieval or "
         "web search. Analyze the input and try to reason about the underlying semantic "
         "intent. Output ONLY the rewritten question, nothing else."),
        ("human", "Original question: {question}\n\nRewritten question:"),
    ])

    chain = prompt | _generator_llm
    response = chain.invoke({"question": question})
    new_question = response.content.strip()

    print(f"[Self-RAG | Rewrite] New question: {new_question[:80]}...")
    return {"question": new_question}


# ---------------------------------------------------------------------------
# 5. Conditional Routing Functions
# ---------------------------------------------------------------------------

def route_after_question(state: SelfRagState) -> str:
    """After route_question: go to retrieve or web_search."""
    if state.get("web_search_needed", False):
        return "web_search_node"
    return "retrieve"


def route_after_grading(state: SelfRagState) -> str:
    """After grade_documents: if relevant docs exist → generate, else → web search."""
    if state.get("web_search_needed", False):
        return "web_search_node"
    return "generate"


def check_hallucinations_and_answer(state: SelfRagState) -> str:
    """
    After generate:
    1. Run HallucinationGrader — if hallucinated (binary_score='no') and loop_count < 3 → regenerate
    2. If grounded (binary_score='yes'), run AnswerGrader
       - If doesn't answer ('no') → rewrite_question
       - If answers ('yes') → END
    """
    _init_components()
    generation = state.get("generation", "")
    documents = state.get("documents", [])
    question = state["question"]
    loop_count = state.get("loop_count", 0)

    docs_text = "\n\n".join(documents)

    # Step 1: Check for hallucinations
    print("[Self-RAG | Check] Running hallucination grader...")
    try:
        hallucination_result = _hallucination_grader.invoke({
            "documents": docs_text,
            "generation": generation,
        })
        is_grounded = hallucination_result.binary_score.lower() == "yes"
    except Exception as e:
        print(f"[Self-RAG | Check] Hallucination grader error: {e}. Assuming grounded.")
        is_grounded = True

    if not is_grounded:
        print(f"[Self-RAG | Check] ❌ Hallucination detected! (loop {loop_count}/3)")
        if loop_count < 3:
            return "generate"  # Retry generation
        else:
            print("[Self-RAG | Check] Max loops reached. Accepting generation.")
            return END

    print("[Self-RAG | Check] ✅ Generation is grounded in documents.")

    # Step 2: Check if it answers the question
    print("[Self-RAG | Check] Running answer grader...")
    try:
        answer_result = _answer_grader.invoke({
            "question": question,
            "generation": generation,
        })
        answers_question = answer_result.binary_score.lower() == "yes"
    except Exception as e:
        print(f"[Self-RAG | Check] Answer grader error: {e}. Assuming it answers.")
        answers_question = True

    if not answers_question:
        print("[Self-RAG | Check] ❌ Generation does not answer the question. Rewriting...")
        if loop_count < 3:
            return "rewrite_question"
        else:
            print("[Self-RAG | Check] Max loops reached. Accepting generation.")
            return END

    print("[Self-RAG | Check] ✅ Generation answers the question. Done!")
    return END


# ---------------------------------------------------------------------------
# 6. Compile the Self-RAG Graph
# ---------------------------------------------------------------------------

def build_self_rag_graph() -> StateGraph:
    """Builds and compiles the Self-RAG state machine."""

    workflow = StateGraph(SelfRagState)

    # Add nodes
    workflow.add_node("route_question", route_question)
    workflow.add_node("retrieve", retrieve)
    workflow.add_node("web_search_node", web_search_node)
    workflow.add_node("grade_documents", grade_documents)
    workflow.add_node("generate", generate)
    workflow.add_node("rewrite_question", rewrite_question)

    # Edges
    workflow.add_edge(START, "route_question")

    # After routing: retrieve from index or web search
    workflow.add_conditional_edges("route_question", route_after_question, {
        "retrieve": "retrieve",
        "web_search_node": "web_search_node",
    })

    # After retrieval: grade the documents
    workflow.add_edge("retrieve", "grade_documents")

    # After grading: generate if docs are good, else web search
    workflow.add_conditional_edges("grade_documents", route_after_grading, {
        "generate": "generate",
        "web_search_node": "web_search_node",
    })

    # After web search: go directly to generate (web results are used as-is)
    workflow.add_edge("web_search_node", "generate")

    # After generate: check hallucinations and answer quality
    workflow.add_conditional_edges("generate", check_hallucinations_and_answer, {
        "generate": "generate",        # Hallucination → retry
        "rewrite_question": "rewrite_question",  # Doesn't answer → rewrite
        END: END,                       # All good → done
    })

    # After rewrite: go back to retrieve
    workflow.add_edge("rewrite_question", "retrieve")

    return workflow.compile()


# Compile the graph at module level
self_rag_graph = build_self_rag_graph()
"""The compiled Self-RAG sub-graph. Invoke with:
   result = self_rag_graph.invoke({"question": "...", "documents": [], "generation": "", "loop_count": 0})
"""
