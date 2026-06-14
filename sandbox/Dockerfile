# ─────────────────────────────────────────────────────────────
# ExplainAI Code-Execution Sandbox (Python + C + C++)
#
# Build:   docker build -t explainai-sandbox ./sandbox
# Run:     docker run -i --rm --network none explainai-sandbox
# ─────────────────────────────────────────────────────────────

FROM python:3.12-slim

# Install Curl, GCC/G++, Java, and OpenCV dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        curl ca-certificates gnupg gcc g++ default-jre default-jdk \
        libgl1 libglib2.0-0 && \
    curl -fsSL https://deb.nodesource.com/setup_22.x | bash - && \
    apt-get install -y --no-install-recommends nodejs && \
    rm -rf /var/lib/apt/lists/*

# Install FastMCP and requested data science/utility libraries
RUN pip install --no-cache-dir \
    "fastmcp>=2.0.0" \
    numpy pandas matplotlib scipy sympy scikit-learn seaborn plotly \
    jupyter requests beautifulsoup4 lxml networkx pillow opencv-python

# Copy the MCP server script
COPY server.py /app/server.py
WORKDIR /app

# The MCP client connects via stdio (stdin/stdout JSON-RPC)
ENTRYPOINT ["python", "server.py"]
