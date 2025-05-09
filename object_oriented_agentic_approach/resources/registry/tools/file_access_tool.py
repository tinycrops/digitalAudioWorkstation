import subprocess
import os
import soundfile as sf # Added for metadata extraction
from moviepy.video.io.VideoFileClip import VideoFileClip # Updated for moviepy v2.x
from typing import Dict, Any

from ...object_oriented_agents.utils.logger import get_logger
from ...object_oriented_agents.core_classes.tool_interface import ToolInterface

class FileAccessTool(ToolInterface):
    """
    A tool to prepare media files (audio/video) for processing by copying them to a Docker container
    and extracting basic metadata.
    """

    def __init__(self, logger=None):
        self.logger = logger or get_logger(self.__class__.__name__)

    def get_definition(self) -> Dict[str, Any]:
        self.logger.debug("Returning tool definition for prepare_media_file_for_processing")
        return {
            "function": {
                "name": "prepare_media_file_for_processing",
                "description": (
                    "Verifies a host media file (audio or video), copies it into the sandboxed Docker container's "
                    "'/home/sandboxuser/input_audio/' directory, and extracts its metadata (e.g., duration, sample rate, channels for audio; duration, resolution, fps for video)."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "host_media_file_path": {
                            "type": "string",
                            "description": "The path to the media file (audio or video) on the host system."
                        }
                    },
                    "required": ["host_media_file_path"]
                }
            }
        }

    def run(self, arguments: Dict[str, Any]) -> str:
        host_media_file_path = arguments["host_media_file_path"]
        self.logger.debug(f"Running prepare_media_file_for_processing with host_media_file_path: {host_media_file_path}")
        return self.prepare_media_file(host_media_file_path)

    def _get_file_type(self, file_path: str) -> str:
        _, ext = os.path.splitext(file_path)
        ext = ext.lower()
        # Define known audio and video extensions
        audio_extensions = ['.wav', '.mp3', '.flac', '.ogg', '.aac']
        video_extensions = ['.mp4', '.mov', '.avi', '.mkv', '.webm', '.flv'] # .webm can be video too
        
        if ext in audio_extensions:
            return "audio"
        if ext in video_extensions:
            return "video"
        if ext == '.webm': # WebM can be tricky, could be audio-only or video.
            # A more robust check might involve ffprobe, but for now, lean towards video if not strictly audio extension
            try:
                with VideoFileClip(file_path) as clip: # Attempt to open as video
                    if clip.audio is None and clip.duration > 0 and clip.size != (0,0) : # has video frames
                        return "video"
                    elif clip.audio is not None and clip.size == (0,0): # audio only in video container
                         return "audio"
            except Exception: # If it fails to open as video, might be audio or unknown
                 pass # Fall through to generic or soundfile check
            # If it has common audio codecs it might be audio. Default to "video" for webm if ambiguous or treat as unknown.
            # For simplicity, if not clearly audio by other extensions, and it's webm, let video path try it.
            return "video" 
        return "unknown"

    def prepare_media_file(self, host_media_file_path: str, container_name: str = "sandbox") -> str:
        self.logger.info(f"Preparing media file: {host_media_file_path}")

        if not os.path.isfile(host_media_file_path):
            error_msg = f"Error: The host media file '{host_media_file_path}' was not found."
            self.logger.error(error_msg)
            return error_msg

        metadata_str = "Metadata: Could not determine file type or extract details."
        file_type = self._get_file_type(host_media_file_path)
        self.logger.info(f"Determined file type for {host_media_file_path}: {file_type}")

        try:
            if file_type == "audio":
                audio_info = sf.info(host_media_file_path)
                metadata_str = (
                    f"Metadata (Audio): Duration: {audio_info.duration:.2f}s, "
                    f"Sample Rate: {audio_info.samplerate}Hz, "
                    f"Channels: {audio_info.channels}, "
                    f"Format: {audio_info.format} (Subtype: {audio_info.subtype})"
                )
            elif file_type == "video":
                with VideoFileClip(host_media_file_path) as clip:
                    metadata_str = (
                        f"Metadata (Video): Duration: {clip.duration:.2f}s, "
                        f"Resolution: {clip.size[0]}x{clip.size[1]}, "
                        f"FPS: {clip.fps:.2f}"
                    )
            self.logger.info(f"Extracted metadata for {host_media_file_path}: {metadata_str}")
        except Exception as e:
            error_msg = f"Warning: Error extracting specific {file_type} metadata from '{host_media_file_path}': {str(e)}. Will proceed with copy."
            self.logger.error(error_msg, exc_info=True)
            metadata_str = f"Metadata: Partial or no details extracted ({e}), but proceeding with file copy."
            self.logger.info("Proceeding with file copy despite metadata extraction failure")

        try:
            container_input_dir = "/home/sandboxuser/input_audio"
            copied_file_container_path = self.copy_file_to_container(
                host_local_file_path=host_media_file_path,
                container_name=container_name,
                container_target_dir=container_input_dir
            )
            
            success_message = (
                f"Media file prepared. Ready in sandbox at: {copied_file_container_path}\n"
                f"{metadata_str}"
            )
            self.logger.info(success_message)
            return success_message
            
        except FileNotFoundError as e: # From copy_file_to_container if host file suddenly disappears
            self.logger.error(f"File not found during copy: {str(e)}")
            return str(e)
        except RuntimeError as e: # From copy_file_to_container for Docker errors
            self.logger.error(f"Runtime error during copy: {str(e)}")
            return str(e)
        except Exception as e:
            error_msg = f"Unexpected error while preparing media file '{host_media_file_path}': {str(e)}"
            self.logger.error(error_msg, exc_info=True)
            return error_msg

    def copy_file_to_container(self, host_local_file_path: str, container_name: str, container_target_dir: str) -> str:
        self.logger.debug(f"Copying '{host_local_file_path}' to container '{container_name}' into directory '{container_target_dir}'.")

        if not os.path.isfile(host_local_file_path):
            error_msg = f"The local file '{host_local_file_path}' does not exist for copying."
            self.logger.error(error_msg)
            raise FileNotFoundError(error_msg) # Raise to be caught by calling method

        # Check if container is running
        check_container_cmd = ["docker", "inspect", "-f", "{{.State.Running}}", container_name]
        try:
            result = subprocess.run(check_container_cmd, capture_output=True, text=True, check=True, timeout=5)
            if result.stdout.strip() != "true":
                error_msg = f"The container '{container_name}' is not running or in an unexpected state."
                self.logger.error(error_msg)
                raise RuntimeError(error_msg)
        except subprocess.CalledProcessError as e:
            error_msg = f"Error checking container status for '{container_name}': {e.stderr or e.stdout or str(e)}"
            self.logger.error(error_msg)
            raise RuntimeError(error_msg)
        except subprocess.TimeoutExpired:
            error_msg = f"Timeout while checking status of container '{container_name}'."
            self.logger.error(error_msg)
            raise RuntimeError(error_msg)
            
        # Ensure the target directory exists in the container
        mkdir_cmd = ["docker", "exec", container_name, "mkdir", "-p", container_target_dir]
        try:
            subprocess.run(mkdir_cmd, check=True, capture_output=True, text=True, timeout=5)
            self.logger.info(f"Ensured directory '{container_target_dir}' exists in container '{container_name}'.")
        except subprocess.CalledProcessError as e:
            error_msg = f"Failed to create directory '{container_target_dir}' in container '{container_name}': {e.stderr or e.stdout or str(e)}"
            self.logger.error(error_msg)
            raise RuntimeError(error_msg) # Propagate as a runtime error
        except subprocess.TimeoutExpired:
            error_msg = f"Timeout while creating directory '{container_target_dir}' in container '{container_name}'."
            self.logger.error(error_msg)
            raise RuntimeError(error_msg)

        # Define the full path for the file inside the container
        base_filename = os.path.basename(host_local_file_path)
        container_full_file_path = os.path.join(container_target_dir, base_filename) # POSIX path for container

        # Copy the file into the container
        docker_cp_path = f"{container_name}:{container_full_file_path}"
        self.logger.debug(f"Running command: docker cp '{host_local_file_path}' '{docker_cp_path}'")
        try:
            subprocess.run(["docker", "cp", host_local_file_path, docker_cp_path], check=True, capture_output=True, text=True, timeout=30) # Added timeout
        except subprocess.CalledProcessError as e:
            error_msg = f"Failed to copy '{host_local_file_path}' to '{docker_cp_path}': {e.stderr or e.stdout or str(e)}"
            self.logger.error(error_msg)
            raise RuntimeError(error_msg)
        except subprocess.TimeoutExpired:
            error_msg = f"Timeout while copying '{host_local_file_path}' to '{docker_cp_path}'."
            self.logger.error(error_msg)
            raise RuntimeError(error_msg)

        # Verify the file was copied (optional, but good practice)
        verify_cmd = ["docker", "exec", container_name, "test", "-f", container_full_file_path]
        try:
            subprocess.run(verify_cmd, check=True, capture_output=True, text=True, timeout=5)
        except subprocess.CalledProcessError: # Not logging stdout/stderr as it's usually empty on success or non-indicative for test -f
            error_msg = f"Failed to verify the file '{container_full_file_path}' in the container '{container_name}'."
            self.logger.error(error_msg)
            raise RuntimeError(error_msg)
        except subprocess.TimeoutExpired:
            error_msg = f"Timeout during verification of '{container_full_file_path}' in container '{container_name}'."
            self.logger.error(error_msg)
            raise RuntimeError(error_msg)
            
        success_msg = f"Copied '{host_local_file_path}' to '{docker_cp_path}'."
        self.logger.info(success_msg)
        return container_full_file_path # Return the path inside the container