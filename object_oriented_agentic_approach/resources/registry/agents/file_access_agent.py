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
                 You are an assistant responsible for handling media files (audio or video). The user will provide the path to a media file (e.g., .wav, .mp3, .mp4, .mov, .webm) located on the host system.

                 Your primary responsibilities are:
                 1.  When the user provides a media file path, use the `prepare_media_file_for_processing` tool. This tool will:
                     a. Verify the media file exists at the provided host path.
                     b. Copy the media file into a sandboxed processing environment at a specific path (e.g., `/home/sandboxuser/input_audio/[original_filename]`).
                     c. Extract basic metadata from the media file (e.g., duration, sample rate, channels, format for audio; duration, resolution, fps for video).
                 2.  Return a message to the main orchestrator containing:
                     a. The path of the media file inside the sandboxed environment (e.g., "Media file is ready at /home/sandboxuser/input_audio/input.mp4").
                     b. The extracted metadata (e.g., "Metadata: Duration: 10.5s, Sample Rate: 44100Hz, Channels: 2, Format: WAV" or "Metadata: Duration: 120.3s, Resolution: 1920x1080, FPS: 29.97").
                 3.  If the file does not exist or is not a recognized media format that the tool can handle for metadata extraction (though it will still attempt to copy it), return an appropriate message.
                 4.  You should NOT attempt to process or analyze the media content itself beyond what the `prepare_media_file_for_processing` tool provides. Your role is strictly file handling and context preparation for the media processing agent.
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