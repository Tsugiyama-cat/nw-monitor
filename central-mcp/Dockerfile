FROM node:22-slim

RUN apt-get update \
 && apt-get install -y --no-install-recommends curl ca-certificates python3 \
 && rm -rf /var/lib/apt/lists/* \
 && curl -LsSf https://astral.sh/uv/install.sh | sh

ENV PATH="/root/.local/bin:${PATH}"

RUN npm install -g supergateway

EXPOSE 8811

# stdioのcentral-mcp-serverをstreamable HTTP (/mcp) で公開
CMD ["supergateway", \
     "--stdio", "uvx --prerelease=allow central-mcp-server", \
     "--outputTransport", "streamableHttp", \
     "--streamableHttpPath", "/mcp", \
     "--port", "8811"]
