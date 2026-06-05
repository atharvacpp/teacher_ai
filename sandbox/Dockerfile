# ─────────────────────────────────────────────────────────────
# ExplainAI Code-Execution Sandbox (Python + C + C++)
#
# Build:   docker build -t explainai-sandbox ./sandbox
# Run:     docker run -i --rm --network none explainai-sandbox
# ─────────────────────────────────────────────────────────────

FROM python:3.12-slim

# Install GCC/G++ for C/C++ compilation alongside Python
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc g++ && \
    rm -rf /var/lib/apt/lists/*

# Install FastMCP (includes MCP SDK as a transitive dependency)
RUN pip install --no-cache-dir "fastmcp>=2.0.0"

# Copy the MCP server script
COPY server.py /app/server.py
WORKDIR /app

# The MCP client connects via stdio (stdin/stdout JSON-RPC)
ENTRYPOINT ["python", "server.py"]
