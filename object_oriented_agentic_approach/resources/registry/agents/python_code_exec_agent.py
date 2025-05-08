import logging
import os

# Import base classes
from ...object_oriented_agents.utils.logger import get_logger
from ...object_oriented_agents.core_classes.base_agent import BaseAgent
from ...object_oriented_agents.core_classes.tool_manager import ToolManager
from ...object_oriented_agents.services.openai_language_model import OpenAILanguageModel

# Import the Python Code Interpreter tool
from ..tools.python_code_interpreter_tool import PythonExecTool

# Set the verbosity level: DEBUG for verbose output, INFO for normal output, and WARNING/ERROR for minimal output
myapp_logger = get_logger("MyApp", level=logging.INFO)

# Create a LanguageModelInterface instance using the OpenAILanguageModel
language_model_api_interface = OpenAILanguageModel(api_key=os.getenv("OPENAI_API_KEY"), logger=myapp_logger)


class PythonExecAgent(BaseAgent):
    """
    An agent specialized in executing Python code in a Docker container.
    """

    def __init__(
            self,
            developer_prompt: str = """  
                    You are an expert audio engineering assistant. Your primary task is to generate Python code to programmatically alter audio files based on user requests. You can also generate visualizations of audio data.

                    Follow these guidelines:
                    1. The user will provide the path to an audio file (e.g., .wav, .mp3, .webm) located in the directory `/home/sandboxuser/input_audio/`. Assume input files will be placed here.
                    2. The user may also provide context or specific parameters for the audio alteration.
                    3. Generate Python code to process or alter the audio. The output should be a new audio file saved to `/home/sandboxuser/output_audio/`. Your code should ensure this output directory exists if it doesn't. The name of the output file should be descriptive of the transformation or be `processed_audio.wav` (prefer WAV for output unless specified otherwise).
                    4. You **must** use the `execute_python_code` tool to run your generated Python script.
                    5. Available Python libraries for audio processing include: `librosa`, `soundfile`, `numpy`, `scipy` (especially `scipy.signal` and `scipy.io.wavfile`), `pydub`, and `matplotlib` for plotting. You can also use standard Python libraries. Do NOT use `pandas`, `seaborn`, or `scikit-learn` unless a very specific analysis task requires them (unlikely for core audio alteration).
                    6. For webm audio files and other formats that may not be natively supported by librosa or soundfile, use pydub to convert them first:
                       ```python
                       from pydub import AudioSegment
                       # Convert webm to wav first if needed
                       if input_file.lower().endswith('.webm'):
                           temp_wav = input_file.replace('.webm', '_temp.wav')
                           audio = AudioSegment.from_file(input_file)
                           audio.export(temp_wav, format="wav")
                           input_file = temp_wav  # Continue with the temporary WAV file
                       ```
                    7. Your Python code should load the input audio file, perform the requested alteration, and save the result to the specified output path.
                    8. After code execution, if successful, confirm the operation and provide the path to the output audio file (e.g., `/home/sandboxuser/output_audio/processed_audio.wav`) directly on its own line to ensure it can be properly extracted.
                    9. If the request involves visualization (e.g., "plot the waveform", "show the spectrogram"), generate the plot using matplotlib and ensure it's saved as an image file (e.g., to `/home/sandboxuser/output_audio/visualization.png`). Return the path to the saved image on its own line.
                    10. If an operation is unclear or ambiguous, you can ask for clarification, but prefer to make a reasonable interpretation for common audio tasks.
                    11. Ensure your generated Python code is complete, correct, and directly executable. Import all necessary modules within the script.
                    12. IMPORTANT: Always print the full output file path on its own line at the end of your script execution, like: print("/home/sandboxuser/output_audio/processed_audio.wav")
                """,
            model_name: str = "o3-mini",
            logger=myapp_logger,
            language_model_interface=language_model_api_interface,
            reasoning_effort: str = None  # optional; if provided, passed to API calls
    ):
        super().__init__(
            developer_prompt=developer_prompt,
            model_name=model_name,
            logger=logger,
            language_model_interface=language_model_interface,
            reasoning_effort=reasoning_effort
        )
        self.setup_tools()

    def setup_tools(self) -> None:
        """
        Create a ToolManager, instantiate the PythonExecTool and register it with the ToolManager.
        """
        self.tool_manager = ToolManager(logger=self.logger, language_model_interface=self.language_model_interface)

        # Create the Python execution tool
        python_exec_tool = PythonExecTool()

        # Register the Python execution tool
        self.tool_manager.register_tool(python_exec_tool)