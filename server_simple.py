import uvicorn
from dotenv import load_dotenv
from pydantic_ai import Agent

load_dotenv()

# Create a simple agent without MCP to test basic A2A functionality
agent = Agent(
    "openai:gpt-4o-mini",
    instructions="You are a helpful assistant. Answer questions directly without using any external tools."
)

app = agent.to_a2a(
    name="Simple Test Agent",
    description="A basic agent for testing A2A functionality without MCP servers.",
    url="http://localhost:7000"
)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=7000)