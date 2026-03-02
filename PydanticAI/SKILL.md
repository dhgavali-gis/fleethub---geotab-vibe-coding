# SKILL.md: PydanticAI Development Standards

## 1. Core Philosophy

You are an expert AI Engineer specializing in **PydanticAI (2026 Edition)**. You prioritize **Type-Safety**, **Structured Outputs**, and **Dependency Injection** over loose scripting.

* **Architecture over Logic:** Focus on the "Shape" of the data first. Define the result models before writing the agent logic.
* **Stateless over Stateful:** Use the framework's `RunContext` to manage state through dependencies rather than global variables.

---

## 2. Structural Requirements

### 2.1 Result Modeling

Every Agent must have a defined `result_type`. This ensures the AI decomposes tasks into a format that the application can programmatically use (e.g., for UI rendering or database writes).

```python
from pydantic import BaseModel, Field
from typing import List, Optional

class TaskStep(BaseModel):
    tool_used: str
    summary: str

class AgentResponse(BaseModel):
    final_answer: str
    steps_taken: List[TaskStep]
    confidence_score: float = Field(ge=0, le=1)

```

### 2.2 Dependency Injection (The `deps` Pattern)

All external service clients (APIs, Databases, Protocol Handlers) must be encapsulated in a `dataclass` and passed via the `deps_type`.

```python
from dataclasses import dataclass

@dataclass
class SystemDeps:
    api_client: Any
    spatial_tool: Any
    config: dict

```

### 2.3 Agent Initialization

Always explicitly declare types to enable static analysis and better LLM reasoning.

```python
from pydantic_ai import Agent

agent = Agent(
    'google-gla:gemini-3-flash', # Recommended for speed and reasoning
    deps_type=SystemDeps,
    result_type=AgentResponse,
    system_prompt="Your role is a task orchestrator..."
)

```

---

## 3. Agentic Workflow & Task Decomposition

### 3.1 Reasoning Loop (The "Decompose" Pattern)

The Agent should be prompted to act as a **Planner-Executor**:

1. **Decomposition:** Break a complex user query into atomic sub-tasks.
2. **Tool Selection:** Match sub-tasks to available `@agent.tool` functions.
3. **Synthesis:** Aggregate tool outputs into the final `result_type`.

### 3.2 Tool Definition Standards

Tools must have detailed docstrings. The LLM uses these docstrings as its primary "manual" for understanding when and how to call the function.

```python
@agent.tool
async def fetch_real_time_data(ctx: RunContext[SystemDeps], query_params: dict):
    """
    Fetches live data from the primary data source. 
    Use this when the user asks for the 'current' or 'live' status.
    """
    return await ctx.deps.api_client.get(query_params)

```

---

## 4. Integration with Web Frameworks (e.g., FastAPI)

When integrating with an API layer, follow the **Bridge Pattern**:

* **FastAPI** handles the HTTP request/response.
* **PydanticAI** handles the internal reasoning logic.

```python
@app.post("/ask")
async def handle_request(query: str):
    # Initialize dependencies within the route or inject them
    deps = SystemDeps(api_client=global_client)
    
    # Run the agentic loop
    result = await agent.run(query, deps=deps)
    
    # Return the structured data directly
    return result.data

```

---

## 5. Performance & Concurrency

* **Async First:** All tools and agent runs must be `async`.
* **Parallel Tool Execution:** If tasks are independent, use `asyncio.gather` within a tool or wrapper to trigger multiple calls simultaneously to reduce latency.

---

## 6. Debugging & Observability

* **Logfire Integration:** Every PydanticAI project should enable `logfire` for real-time tracing of the reasoning chain.
* **Prompt Iteration:** If the Agent fails to decompose a task correctly, refine the `system_prompt` in the Agent definition rather than adding complex `if/else` logic in the code.

---

## 7.  Instruction Shortcuts

* **"Decompose this":** "Using PydanticAI patterns, create an agent that decomposes [user query] into [list of tools]."
* **"Add Tooling":** "Add an async tool to the current agent that utilizes `ctx.deps` to perform [specific action]."
* **"Type-Safe Response":** "Define a Pydantic model for the agent output that includes [specific fields] and enforce it using `result_type`."

---