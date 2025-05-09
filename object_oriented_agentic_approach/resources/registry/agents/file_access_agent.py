import logging
import os

# Import base classes
from ...object_oriented_agents.utils.logger import get_logger
from ...object_oriented_agents.core_classes.base_agent import BaseAgent
from ...object_oriented_agents.core_classes.tool_manager import ToolManager
from ...object_oriented_agents.services.openai_language_model import OpenAILanguageModel

# Import the Tool
from ..tools.file_access_tool import FileAccessTool

# Set the verbosity level: DEBUG for verbose output, INFO for normal output, and WARNING/ERROR for minimal output
myapp_logger = get_logger("MyApp", level=logging.INFO)

# Create a LanguageModelInterface instance using the OpenAILanguageModel
language_model_api_interface = OpenAILanguageModel(api_key=os.getenv("OPENAI_API_KEY"), logger=myapp_logger)


class FileAccessAgent(BaseAgent):
    """
    Agent that can only use the 'safe_file_access' tool to read CSV files.
    """
    # We pass the Agent attributes in the constructor 
    def __init__(self, 
                 developer_prompt: str = """
                 You are an assistant responsible for handling audio files. The user will provide the path to an audio file (e.g., .wav, .mp3) located on the host system.

                 Your primary responsibilities are:
                 1.  When the user provides an audio file path, use the `prepare_audio_file_for_processing` tool. This tool will:
                     a. Verify the audio file exists at the provided host path.
                     b. Copy the audio file into a sandboxed processing environment at a specific path (e.g., `/home/sandboxuser/input_audio/[original_filename]`).
                     c. Extract basic metadata from the audio file (e.g., duration, sample rate, channels, format).
                 2.  Return a message to the main orchestrator containing:
                     a. The path of the audio file inside the sandboxed environment (e.g., "Audio file is ready at /home/sandboxuser/input_audio/input.wav").
                     b. The extracted metadata (e.g., "Metadata: Duration: 10.5s, Sample Rate: 44100Hz, Channels: 2, Format: WAV").
                 3.  If the file does not exist or is not a recognized audio format that the tool can handle, return an appropriate error message.
                 4.  You should NOT attempt to process or analyze the audio content itself beyond what the `prepare_audio_file_for_processing` tool provides. Your role is strictly file handling and context preparation for the audio processing agent.
                 5.  Do not include any additional commentary beyond the file path in the sandbox and its metadata.
                 """,
                 model_name: str = "gpt-4.1-mini",
                 logger = myapp_logger,
                 language_model_interface = language_model_api_interface):
        super().__init__(developer_prompt=developer_prompt, model_name=model_name, logger=logger, language_model_interface=language_model_interface)
        self.setup_tools()

    def setup_tools(self) -> None:
        self.logger.debug("Setting up tools for FileAccessAgent.")
        # Pass the openai_client to ToolManager
        self.tool_manager = ToolManager(logger=self.logger, language_model_interface=self.language_model_interface)
        # Register the one tool this agent is allowed to use
        self.tool_manager.register_tool(FileAccessTool(logger=self.logger))