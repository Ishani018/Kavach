import inspect
from agentdojo.agent_pipeline.llms.prompting_llm import PromptingLLM
print(inspect.getsource(PromptingLLM._get_system_message))
