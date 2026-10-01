# entity-chat

Extracts named entities from a PDF with GLiNER and answers questions about them with Claude.

```
export ANTHROPIC_API_KEY=<your_anthropic_api_key>

uv sync
uv run entity-chat document.pdf "How many mentions of Pydantic are there?" \
    --labels technology,organization
```
