import subprocess
import os
from typing import Dict, Any

from ...object_oriented_agents.utils.logger import get_logger
from ...object_oriented_agents.core_classes.tool_interface import ToolInterface

class RetrieveOutputTool(ToolInterface):
    """
    A tool to retrieve files (e.g., processed audio, visualizations) from the Docker sandbox
    to a specified directory on the host machine.
    """

    def __init__(self, logger=None):
        self.logger = logger or get_logger(self.__class__.__name__)

    def get_definition(self) -> Dict[str, Any]:
        self.logger.debug("Returning tool definition for retrieve_output_from_sandbox")
        return {
            "function": {
                "name": "retrieve_output_from_sandbox",
                "description": (
                    "Copies a specified file from the Docker sandbox container "
                    "to a target directory on the host system."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "container_file_path": {
                            "type": "string",
                            "description": "The full path to the file inside the sandbox container (e.g., /home/sandboxuser/output_audio/processed.wav)."
                        },
                        "host_target_dir": {
                            "type": "string",
                            "description": "The path to an existing directory on the host system where the file should be copied."
                        }
                    },
                    "required": ["container_file_path", "host_target_dir"]
                }
            }
        }

    def run(self, arguments: Dict[str, Any]) -> str:
        container_file_path = arguments["container_file_path"]
        host_target_dir = arguments["host_target_dir"]
        
        self.logger.info(f"Attempting to retrieve '{container_file_path}' from sandbox to host directory '{host_target_dir}'.")

        if not os.path.isdir(host_target_dir):
            error_msg = f"Error: Host target directory '{host_target_dir}' does not exist or is not a directory."
            self.logger.error(error_msg)
            return error_msg

        container_name = "sandbox" # Assuming the standard container name

        # Check if container is running
        check_container_cmd = ["docker", "inspect", "-f", "{{.State.Running}}", container_name]
        try:
            result = subprocess.run(check_container_cmd, capture_output=True, text=True, check=True, timeout=5)
            if result.stdout.strip() != "true":
                error_msg = f"The container '{container_name}' is not running or in an unexpected state."
                self.logger.error(error_msg)
                return f"Error: {error_msg}"
        except subprocess.CalledProcessError as e:
            error_msg = f"Error checking container status for '{container_name}': {e.stderr or e.stdout or str(e)}"
            self.logger.error(error_msg)
            return f"Error: {error_msg}"
        except subprocess.TimeoutExpired:
            error_msg = f"Timeout while checking status of container '{container_name}'."
            self.logger.error(error_msg)
            return f"Error: {error_msg}"

        # Check if the file exists in the container before attempting to copy
        check_file_cmd = ["docker", "exec", container_name, "test", "-f", container_file_path]
        try:
            subprocess.run(check_file_cmd, check=True, capture_output=True, text=True, timeout=5)
            self.logger.debug(f"File '{container_file_path}' confirmed to exist in container '{container_name}'.")
        except subprocess.CalledProcessError:
            error_msg = f"Error: File '{container_file_path}' not found in container '{container_name}'."
            self.logger.error(error_msg)
            return error_msg
        except subprocess.TimeoutExpired:
            error_msg = f"Timeout checking for file '{container_file_path}' in container '{container_name}'."
            self.logger.error(error_msg)
            return error_msg

        # Prepare host destination path
        base_filename = os.path.basename(container_file_path)
        host_destination_path = os.path.join(host_target_dir, base_filename)
        
        docker_cp_source = f"{container_name}:{container_file_path}"
        self.logger.debug(f"Running command: docker cp '{docker_cp_source}' '{host_destination_path}'")

        try:
            subprocess.run(["docker", "cp", docker_cp_source, host_destination_path], check=True, capture_output=True, text=True, timeout=30)
            success_msg = f"Successfully retrieved '{container_file_path}' to '{host_destination_path}'."
            self.logger.info(success_msg)
            return f"File retrieved to: {host_destination_path}"
        except subprocess.CalledProcessError as e:
            error_msg = f"Failed to copy '{docker_cp_source}' to '{host_destination_path}': {e.stderr or e.stdout or str(e)}"
            self.logger.error(error_msg)
            return f"Error: {error_msg}"
        except subprocess.TimeoutExpired:
            error_msg = f"Timeout while copying '{docker_cp_source}' to '{host_destination_path}'."
            self.logger.error(error_msg)
            return f"Error: {error_msg}"
        except Exception as e:
            error_msg = f"An unexpected error occurred during file retrieval: {str(e)}"
            self.logger.error(error_msg, exc_info=True)
            return f"Error: {error_msg}" 